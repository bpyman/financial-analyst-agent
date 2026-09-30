"""HTTP seam for the Next.js audience window (ADR 0006).

Transport only: it calls the conversation seam, maps results through
``present_turn``, and serialises the display records. No financial logic,
no number formatting beyond what ``presentation`` already produced.

Run with ``uv run serve-api`` (uvicorn factory ``create_app``).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import threading
import time
import unicodedata
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from financial_analyst_agent.config import Settings, get_settings
from financial_analyst_agent.conversation import run_conversation_turn, start_thread
from financial_analyst_agent.domain.errors import (
    ConfigurationError,
    RuntimeMismatchError,
    SessionQuotaError,
)
from financial_analyst_agent.news import FIXTURE_NEWS_QUERY
from financial_analyst_agent.observability import configure_logging
from financial_analyst_agent.presentation import metric_groups, present_turn, spec_chips
from financial_analyst_agent.runtime import (
    FIXTURE_EXPLAIN_QUERY,
    FIXTURE_UNIVERSE_SNAPSHOT_PATH,
    _snapshot_ranking,
    default_runtime_kind,
    openai_enabled,
    resolve_runtime_kind,
    runtime_for,
    runtime_locked,
    tavily_enabled,
)
from financial_analyst_agent.session import (
    SessionBudget,
    new_thread_id,
    persist_session_budget,
    snapshot_status,
)
from financial_analyst_agent.storefront import (
    EXAMPLE_QUERY,
    GUIDED_STORIES,
    LIVE_RUNTIME_CAPTION,
    LIVE_RUNTIME_LOCKED_NOTICE,
    RECORDED_BANNER,
    RUNTIME_GUIDE_FOOTER,
    capabilities_for,
    runtime_guide,
)
from financial_analyst_agent.thread_store import LocalThreadStore
from financial_analyst_agent.turn import RuntimeKind, TurnResult

_LOGGER = logging.getLogger("financial_analyst_agent")
PUBLIC_FAILURE_MESSAGE = "The analysis could not be completed. Please try again."
MAX_MESSAGE_CHARS = 2000
TURN_IN_FLIGHT_MESSAGE = "A turn is already running."
UNKNOWN_THREAD_MESSAGE = "Unknown thread."
BUSY_MESSAGE = "The analysis service is busy. Please try again in a moment."
BUSY_RETRY_AFTER_SECONDS = 5
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}
PROXY_TOKEN_HEADER = "x-proxy-token"
# The visitor's address, set by the web proxy from the platform's own header.
CLIENT_IP_HEADER = "x-client-ip"
HEALTH_PATH = "/api/health"
# A turn is one question of at most MAX_MESSAGE_CHARS; nothing needs more.
MAX_BODY_BYTES = 16 * 1024
RATE_LIMITED_MESSAGE = (
    "You've asked a lot of questions in the last hour. Please wait a little and try again."
)


def public_error_message(exc: BaseException) -> str:
    """What a visitor may read about a failed turn: our own errors verbatim, nothing else.

    A ConfigurationError is the operator's to fix ("Set SEC_USER_AGENT…"), so a
    visitor gets the generic message and the log keeps the detail.
    """
    if isinstance(exc, (SessionQuotaError, RuntimeMismatchError)):
        return str(exc)
    return PUBLIC_FAILURE_MESSAGE


def thread_store_root() -> Path:
    """Durable local root for conversation threads (no database server)."""
    return Path(".cache") / "threads"


class ProxyTokenGuard:
    """Refuse every request but the health check that lacks the proxy's shared secret.

    The Next.js proxy adds ``X-Proxy-Token`` from ``API_PROXY_TOKEN`` (ADR 0006),
    so a hosted API is not a second public entry point. The comparison is
    constant-time so a wrong guess learns nothing from response timing.
    """

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        self._app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] != HEALTH_PATH:
            presented = b""
            for name, value in scope["headers"]:
                if name == PROXY_TOKEN_HEADER.encode():
                    presented = value
                    break
            if not hmac.compare_digest(presented, self._token):
                refused = JSONResponse({"detail": "Not authorized."}, status_code=401)
                await refused(scope, receive, send)
                return
        await self._app(scope, receive, send)


class BodySizeLimit:
    """Refuse a request body larger than ``limit`` bytes with 413, declared or streamed."""

    def __init__(self, app: ASGIApp, *, limit: int) -> None:
        self._app = app
        self._limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        for name, value in scope["headers"]:
            if name == b"content-length" and value.isdigit() and int(value) > self._limit:
                await _too_large(scope, receive, send)
                return
        received = 0

        async def limited() -> Any:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._limit:
                    raise _BodyTooLarge
            return message

        try:
            await self._app(scope, limited, send)
        except _BodyTooLarge:
            await _too_large(scope, receive, send)


class _BodyTooLarge(Exception):
    pass


async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
    refused = JSONResponse(
        {"detail": "That request is too large for the analysis service."}, status_code=413
    )
    await refused(scope, receive, send)


class ClientRateLimit:
    """At most ``limit`` events per client in any rolling hour, across request threads.

    Keeps timestamps per client only while they fall inside the window, and
    forgets idle clients, so memory follows recent visitors, not all of them.
    """

    def __init__(self, limit: int, *, window_seconds: float = 3600.0) -> None:
        self._limit = limit
        self._window = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._guard = threading.Lock()

    def try_acquire(self, client: str, now: float | None = None) -> float | None:
        """Record an event; ``None`` if allowed, else seconds until one is."""
        moment = time.monotonic() if now is None else now
        cutoff = moment - self._window
        with self._guard:
            idle = [key for key, times in self._events.items() if times[-1] <= cutoff]
            for key in idle:
                del self._events[key]
            times = self._events.setdefault(client, deque())
            while times and times[0] <= cutoff:
                times.popleft()
            if len(times) >= self._limit:
                return times[0] + self._window - moment
            times.append(moment)
            return None


def _normalized_message(value: object) -> object:
    """Drop invisible format and control characters (keeping line breaks), then trim.

    A question made only of zero-width spaces is empty, and trailing spaces do
    not count against the length limit.
    """
    if not isinstance(value, str):
        return value
    kept = "".join(
        char
        for char in unicodedata.normalize("NFKC", value)
        if char in "\n\t" or unicodedata.category(char) not in ("Cf", "Cc", "Cs")
    )
    return kept.strip()


class TurnLocks:
    """The per-thread turn lock: at most one turn, or one Start over, per thread at a time.

    Acquisition never blocks (a busy thread answers 409), so a lock is just
    membership in a set: an entry exists only while its holder runs, and the
    map cannot grow with every thread id a caller names.
    """

    def __init__(self) -> None:
        self._held: set[str] = set()
        self._guard = threading.Lock()

    def try_acquire(self, thread_id: str) -> bool:
        with self._guard:
            if thread_id in self._held:
                return False
            self._held.add(thread_id)
            return True

    def release(self, thread_id: str) -> None:
        with self._guard:
            self._held.discard(thread_id)

    def held(self, thread_id: str) -> bool:
        with self._guard:
            return thread_id in self._held

    def __len__(self) -> int:
        with self._guard:
            return len(self._held)


class TurnSlots:
    """The process-wide cap on turns running at once, across every thread.

    Each turn runs on its own OS thread, and a structured turn fans out to a
    worker pool, so the single API process takes only a few at a time.
    Admission never waits: a full house answers 429 before any work starts.
    A slot is freed when its turn ends, whether or not anyone still listens.
    """

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._running = 0
        self._guard = threading.Lock()

    def try_acquire(self) -> bool:
        with self._guard:
            if self._running >= self._limit:
                return False
            self._running += 1
            return True

    def release(self) -> None:
        with self._guard:
            self._running -= 1

    def __len__(self) -> int:
        with self._guard:
            return self._running


class CreateThreadRequest(BaseModel):
    """``runtime`` omitted means the deployment default (``APP_MODE``)."""

    model_config = ConfigDict(extra="forbid")

    runtime: RuntimeKind | None = None


class TurnRequest(BaseModel):
    """A turn runs on its thread's runtime, so it carries no runtime flag."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)

    @field_validator("message", mode="before")
    @classmethod
    def _clean(cls, value: object) -> object:
        return _normalized_message(value)


def _valid_thread_id(thread_id: str) -> str:
    try:
        parsed = uuid.UUID(thread_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=UNKNOWN_THREAD_MESSAGE) from None
    return str(parsed)


PURGE_INTERVAL_SECONDS = 60


class _Throttle:
    """Says yes at most once per interval, across request threads."""

    def __init__(self, interval_seconds: float) -> None:
        self._interval = interval_seconds
        self._last: datetime | None = None
        self._lock = threading.Lock()

    def due(self, now: datetime) -> bool:
        with self._lock:
            if self._last is not None and (now - self._last).total_seconds() < self._interval:
                return False
            self._last = now
            return True


def _snapshot_as_of(kind: RuntimeKind) -> str:
    # Cached per file version, so a refreshed snapshot shows its new date
    # without a restart.
    path = FIXTURE_UNIVERSE_SNAPSHOT_PATH if kind is RuntimeKind.RECORDED else None
    return _snapshot_ranking(path).snapshot_as_of()


def presentation_json(result: TurnResult) -> dict[str, Any]:
    """``present_turn`` as JSON: chart text and amounts arrive already formatted."""
    return asdict(present_turn(result))


def thread_view(
    store: LocalThreadStore,
    thread_id: str,
    settings: Settings,
    *,
    turn_in_flight: bool = False,
    keep: Callable[[str], bool] = lambda _thread_id: False,
) -> dict[str, Any]:
    """Everything the window needs to draw one thread, as JSON-safe display records.

    ``turn_in_flight`` says a turn is running on the thread (a reloaded window
    polls until it ends); such a thread is not expired however old its last save.
    The store asks ``keep`` again as it decides expiry, for a turn begun since.
    """
    ttl = None if turn_in_flight else settings.thread_ttl_seconds
    state = store.load(thread_id, ttl_seconds=ttl, keep=keep)
    turns: list[dict[str, Any]] = []
    chips: tuple[str, ...] = ()
    pending = False
    turn_count = 0
    if state is not None:
        pending = state.pending_clarification is not None
        turn_count = state.turn_count
        if state.analysis_spec is not None:
            chips = spec_chips(state.analysis_spec)
        results = store.resolve_results(state) if state.evidence_refs else ()
        last = min(len(state.messages), len(results)) - 1
        for index, (message, result) in enumerate(
            zip(state.messages, results, strict=False)
        ):
            turns.append(
                {
                    "index": index,
                    "message": message.content,
                    "presentation": presentation_json(result),
                    "candidate_slugs": list(result.candidates),
                    "clarify_enabled": pending and index == last,
                }
            )
    return {
        "thread_id": thread_id,
        "runtime": state.runtime.value if state is not None and state.runtime else None,
        "turns": turns,
        "spec_chips": list(chips),
        "pending_clarification": pending,
        "turn_count": turn_count,
        "max_turns": settings.max_turns_per_thread,
        "turn_in_flight": turn_in_flight,
    }


def _purge_quietly(
    store: LocalThreadStore, now: datetime, ttl_seconds: int, keep: Callable[[str], bool]
) -> None:
    try:
        store.purge_expired(now=now, ttl_seconds=ttl_seconds, keep=keep)
    except Exception:
        _LOGGER.exception("thread_purge_failed")


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def create_app(
    settings: Settings | None = None,
    *,
    store_root: Path | None = None,
) -> FastAPI:
    configure_logging()
    resolved = settings or get_settings()
    store = LocalThreadStore(store_root or thread_store_root())
    turn_locks = TurnLocks()
    turn_slots = TurnSlots(resolved.max_concurrent_turns)
    purge = _Throttle(PURGE_INTERVAL_SECONDS)

    # The public demo does not publish its API: the docs page loads third-party
    # scripts, and its "Try it out" calls would carry the proxy's token.
    private = not resolved.public_demo
    app = FastAPI(
        title="Onfile API",
        docs_url="/api/docs" if private else None,
        openapi_url="/api/openapi.json" if private else None,
        redoc_url=None,
    )
    app.state.turn_locks = turn_locks
    app.state.turn_slots = turn_slots
    thread_limit = ClientRateLimit(resolved.client_threads_per_hour)
    turn_limit = ClientRateLimit(resolved.client_turns_per_hour)
    trust_client_header = bool(resolved.api_proxy_token.get_secret_value())

    def client_key(request: Request) -> str:
        # Behind the token-checked proxy every call comes from the proxy, which
        # names the visitor; without a token, the socket's peer is the client.
        if trust_client_header:
            named = request.headers.get(CLIENT_IP_HEADER, "").strip()
            if named:
                return named[:64]
        return request.client.host if request.client else "unknown"

    def admit(limit: ClientRateLimit, request: Request) -> None:
        wait = limit.try_acquire(client_key(request))
        if wait is not None:
            raise HTTPException(
                status_code=429,
                detail=RATE_LIMITED_MESSAGE,
                headers={"Retry-After": str(max(1, int(wait) + 1))},
            )

    def require_json(request: Request) -> None:
        # A cross-site form can POST text/plain or form data without a CORS
        # preflight; only this app's own fetches send JSON. An empty body needs
        # no type. (The web proxy also refuses cross-site requests outright.)
        kind = request.headers.get("content-type", "").split(";")[0].strip().lower()
        empty = request.headers.get("content-length", "0") == "0" and (
            "transfer-encoding" not in request.headers
        )
        if kind != "application/json" and not (empty and not kind):
            raise HTTPException(status_code=415, detail="Send the request as JSON.")

    @app.exception_handler(RequestValidationError)
    async def plain_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI's default echoes the rejected input back; say what to fix instead.
        kinds = {error.get("type") for error in exc.errors()}
        if "string_too_long" in kinds:
            detail = (
                f"That message is longer than {MAX_MESSAGE_CHARS:,} characters. "
                "Shorten it and send it again."
            )
        elif "string_too_short" in kinds:
            detail = "Ask a question."
        else:
            detail = "The request was not in the form the analysis service expects."
        return JSONResponse(status_code=422, content={"detail": detail})
    app.add_middleware(BodySizeLimit, limit=MAX_BODY_BYTES)
    proxy_token = resolved.api_proxy_token.get_secret_value()
    if proxy_token:
        app.add_middleware(ProxyTokenGuard, token=proxy_token)
    elif resolved.public_demo:
        _LOGGER.warning(
            "API_PROXY_TOKEN is not set on a public demo: the API answers callers "
            "that bypass the web proxy. Set the same token on the API and the proxy."
        )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.head("/api/health", include_in_schema=False)
    def health_head() -> Response:
        # Uptime monitors often probe with HEAD.
        return Response(status_code=200)

    @app.get("/api/meta")
    def meta(runtime: RuntimeKind | None = None) -> dict[str, Any]:
        """Storefront copy; ``runtime`` picks whose snapshot banner to report."""
        default = default_runtime_kind(resolved)
        kind = resolve_runtime_kind(runtime or default, resolved)
        live = kind is RuntimeKind.LIVE
        banner, stale = snapshot_status(
            _snapshot_as_of(kind),
            stale_after_days=resolved.snapshot_stale_after_days,
            recorded=kind is RuntimeKind.RECORDED,
        )
        return {
            "runtime": {"default": default.value, "locked": runtime_locked(resolved)},
            "runtime_copy": {
                "recorded": RECORDED_BANNER,
                "live": LIVE_RUNTIME_CAPTION,
                "locked": LIVE_RUNTIME_LOCKED_NOTICE,
            },
            "runtime_guide": {
                "runtimes": runtime_guide(
                    live_news=tavily_enabled(resolved), live_essays=openai_enabled(resolved)
                ),
                "footer": RUNTIME_GUIDE_FOOTER,
            },
            "snapshot": {"banner": banner, "stale": stale},
            "example_query": EXAMPLE_QUERY,
            "guided_stories": [
                {"label": label, "question": question} for label, question in GUIDED_STORIES
            ],
            "capabilities": [
                {"description": description, "examples": list(examples)}
                for description, examples in capabilities_for(
                    live_news=live and tavily_enabled(resolved),
                    live_essays=live and openai_enabled(resolved),
                    recorded_news=FIXTURE_NEWS_QUERY,
                    recorded_essay=FIXTURE_EXPLAIN_QUERY,
                )
            ],
            "metric_groups": [
                {"title": title, "names": list(names)} for title, names in metric_groups()
            ],
            "max_message_chars": MAX_MESSAGE_CHARS,
        }

    @app.post("/api/threads", status_code=201)
    def create_thread(
        request: Request,
        body: CreateThreadRequest | None = None,
    ) -> dict[str, str | None]:
        require_json(request)
        admit(thread_limit, request)
        requested = (body.runtime if body else None) or default_runtime_kind(resolved)
        kind = resolve_runtime_kind(requested, resolved)
        state = start_thread(new_thread_id(), kind, store=store)
        return {
            "thread_id": state.thread_id,
            "runtime": kind.value,
            "notice": LIVE_RUNTIME_LOCKED_NOTICE if kind != requested else None,
        }

    @app.get("/api/threads/{thread_id}")
    def get_thread(thread_id: str) -> dict[str, Any]:
        valid = _valid_thread_id(thread_id)
        now = datetime.now(UTC)
        if purge.due(now):
            # Every open window polls this route; the scan grows with the number
            # of threads, so it runs beside the request, never in it.
            threading.Thread(
                target=_purge_quietly,
                args=(store, now, resolved.thread_ttl_seconds, turn_locks.held),
                name="thread-purge",
                daemon=True,
            ).start()
        return thread_view(
            store,
            valid,
            resolved,
            turn_in_flight=turn_locks.held(valid),
            keep=turn_locks.held,
        )

    @app.delete("/api/threads/{thread_id}", status_code=204)
    def delete_thread(thread_id: str) -> Response:
        valid = _valid_thread_id(thread_id)
        if not turn_locks.try_acquire(valid):
            raise HTTPException(status_code=409, detail=TURN_IN_FLIGHT_MESSAGE)
        try:
            store.clear(valid)
        finally:
            turn_locks.release(valid)
        return Response(status_code=204)

    @app.post("/api/threads/{thread_id}/turns")
    async def post_turn(thread_id: str, body: TurnRequest, request: Request) -> StreamingResponse:
        valid = _valid_thread_id(thread_id)
        require_json(request)
        message = body.message
        admit(turn_limit, request)
        if not turn_locks.try_acquire(valid):
            raise HTTPException(status_code=409, detail=TURN_IN_FLIGHT_MESSAGE)
        try:
            # Only a thread this API created takes turns: a made-up id would
            # otherwise start a fresh thread, with a fresh quota, on every call.
            # An expired thread is cleared here, under its turn lock.
            prior = await run_in_threadpool(
                store.load, valid, ttl_seconds=resolved.thread_ttl_seconds
            )
            if prior is None:
                raise HTTPException(status_code=404, detail=UNKNOWN_THREAD_MESSAGE)
            if not turn_slots.try_acquire():
                raise HTTPException(
                    status_code=429,
                    detail=BUSY_MESSAGE,
                    headers={"Retry-After": str(BUSY_RETRY_AFTER_SECONDS)},
                )
        except BaseException:
            turn_locks.release(valid)
            raise

        loop = asyncio.get_running_loop()
        events: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

        def emit(event: str, data: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(events.put_nowait, (event, data))

        def run_turn() -> tuple[str, dict[str, Any]]:
            """The turn's terminal event: the thread view, or a public error."""
            # The budget once its turn is reserved: saved even when the turn fails.
            reserved: SessionBudget | None = None
            try:
                budget = SessionBudget.from_counts(
                    turns=prior.turn_count,
                    live_sec_requests=prior.live_sec_requests,
                    max_turns=resolved.max_turns_per_thread,
                    max_live_sec_requests=resolved.max_live_sec_requests_per_thread,
                )
                budget.consume_turn()
                reserved = budget
                run_conversation_turn(
                    valid,
                    message,
                    runtime_for(
                        prior.runtime or default_runtime_kind(resolved),
                        settings=resolved,
                        budget=budget,
                    ),
                    store=store,
                    on_progress=lambda done, total: emit(
                        "progress", {"done": done, "total": total}
                    ),
                )
            except RuntimeMismatchError as exc:
                # Refused before anything ran: the turn does not count against the quota.
                _LOGGER.warning("api_turn_runtime_mismatch", extra={"details": exc.details})
                return "error", {"message": public_error_message(exc)}
            except ConfigurationError:
                # The deployment's fault, not the visitor's: not charged as a turn.
                _LOGGER.exception("api_turn_misconfigured")
                return "error", {"message": PUBLIC_FAILURE_MESSAGE}
            except Exception as exc:
                _LOGGER.exception("api_turn_failed")
                failed = {"message": public_error_message(exc)}
                if reserved is not None:
                    try:
                        persist_session_budget(store, valid, reserved)
                    except Exception:
                        _LOGGER.exception("api_turn_budget_not_saved")
                return "error", failed
            persist_session_budget(store, valid, budget)
            return "thread", thread_view(store, valid, resolved)

        def work() -> None:
            # Exactly one terminal event per turn, whatever raises; the lock and
            # the slot are released first so the analyst's next turn is never
            # refused. A turn runs to its end even if its reader has gone, and
            # only then frees its slot.
            terminal: tuple[str, dict[str, Any]] = (
                "error",
                {"message": public_error_message(Exception())},
            )
            try:
                terminal = run_turn()
            except Exception:
                _LOGGER.exception("api_turn_failed_after_run")
            finally:
                turn_locks.release(valid)
                turn_slots.release()
                emit(*terminal)

        worker = threading.Thread(target=work, name=f"turn-{valid}", daemon=True)
        try:
            worker.start()
        except BaseException:
            turn_slots.release()
            turn_locks.release(valid)
            raise

        async def stream() -> AsyncIterator[str]:
            yield _sse("progress", {"done": 0, "total": 0})
            while True:
                event, data = await events.get()
                yield _sse(event, data)
                if event in ("thread", "error"):
                    return

        return StreamingResponse(stream(), media_type="text/event-stream", headers=_SSE_HEADERS)

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(
        "financial_analyst_agent.api:create_app",
        factory=True,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
    )
