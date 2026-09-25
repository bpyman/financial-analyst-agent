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
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Receive, Scope, Send

from financial_analyst_agent.config import AppMode, Settings, get_settings
from financial_analyst_agent.conversation import run_conversation_turn, start_thread
from financial_analyst_agent.domain.errors import RuntimeMismatchError
from financial_analyst_agent.observability import configure_logging
from financial_analyst_agent.presentation import (
    chart_value_kind,
    format_chart_amount,
    format_date,
    format_field_name,
    metric_groups,
    present_turn,
    spec_chips,
)
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import (
    FIXTURE_UNIVERSE_SNAPSHOT_PATH,
    default_runtime_kind,
    resolve_runtime_kind,
    runtime_for,
)
from financial_analyst_agent.session import (
    SessionBudget,
    new_thread_id,
    persist_session_budget,
    snapshot_status,
)
from financial_analyst_agent.storefront import (
    CAPABILITIES,
    EXAMPLE_QUERY,
    GUIDED_STORIES,
    LIVE_RUNTIME_CAPTION,
    LIVE_RUNTIME_LOCKED_NOTICE,
    RECORDED_BANNER,
    public_error_message,
    thread_store_root,
)
from financial_analyst_agent.thread_store import LocalThreadStore
from financial_analyst_agent.turn import RuntimeKind, TurnResult

_LOGGER = logging.getLogger("financial_analyst_agent")
MAX_MESSAGE_CHARS = 2000
TURN_IN_FLIGHT_MESSAGE = "A turn is already running."
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}
PROXY_TOKEN_HEADER = "x-proxy-token"
HEALTH_PATH = "/api/health"


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


class CreateThreadRequest(BaseModel):
    """``runtime`` omitted means the deployment default (``APP_MODE``)."""

    model_config = ConfigDict(extra="forbid")

    runtime: RuntimeKind | None = None


class TurnRequest(BaseModel):
    """A turn runs on its thread's runtime, so it carries no runtime flag."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


def _valid_thread_id(thread_id: str) -> str:
    try:
        parsed = uuid.UUID(thread_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown thread.") from None
    return str(parsed)


def recorded_mode(settings: Settings) -> tuple[bool, bool]:
    """(default recorded, switch locked) for this deployment."""
    locked = bool(settings.public_demo) and not settings.demo_live_sec
    return settings.app_mode is AppMode.RECORDED or locked, locked


@lru_cache(maxsize=2)
def _snapshot_as_of(recorded: bool) -> str:
    path = FIXTURE_UNIVERSE_SNAPSHOT_PATH if recorded else None
    return SnapshotRanking.from_path(path).snapshot_as_of()


def _period_label(raw: object) -> str:
    text = str(raw)
    try:
        return format_date(date.fromisoformat(text[:10]))
    except ValueError:
        return text


def presentation_json(result: TurnResult) -> dict[str, Any]:
    """``present_turn`` as JSON, with chart text the client would otherwise format.

    Charts gain ``value_kind`` (axis tick style), ``metric_label`` (axis title),
    and for trend lines ``period_labels`` plus server-formatted ``amounts`` per
    series, so tooltips show the same strings as the table.
    """
    presented = asdict(present_turn(result))
    chart = presented.get("chart")
    if chart is not None:
        metric = str(chart.get("metric") or "")
        chart["value_kind"] = chart_value_kind(metric)
        chart["metric_label"] = format_field_name(metric) if metric else ""
        if chart.get("kind") == "line":
            records = chart["records"]
            chart["period_labels"] = [_period_label(record["Period"]) for record in records]
            chart["series"] = [
                key for key in (records[0] if records else {}) if key != "Period"
            ]
            chart["amounts"] = [
                {
                    key: format_chart_amount(metric, value)
                    for key, value in record.items()
                    if key != "Period"
                }
                for record in records
            ]
    return presented


def thread_view(store: LocalThreadStore, thread_id: str, settings: Settings) -> dict[str, Any]:
    """Everything the window needs to draw one thread, as JSON-safe display records."""
    state = store.load(thread_id, ttl_seconds=settings.thread_ttl_seconds)
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
    }


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
    locks: dict[str, threading.Lock] = {}
    locks_guard = threading.Lock()

    def thread_lock(thread_id: str) -> threading.Lock:
        with locks_guard:
            return locks.setdefault(thread_id, threading.Lock())

    app = FastAPI(
        title="Financial analyst agent",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
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

    @app.get("/api/meta")
    def meta(recorded: bool | None = Query(default=None)) -> dict[str, Any]:
        default_recorded, locked = recorded_mode(resolved)
        use_recorded = locked or (default_recorded if recorded is None else recorded)
        banner, stale = snapshot_status(
            _snapshot_as_of(use_recorded),
            stale_after_days=resolved.snapshot_stale_after_days,
        )
        return {
            "recorded": {"default": default_recorded, "locked": locked},
            "runtime_copy": {"recorded": RECORDED_BANNER, "live": LIVE_RUNTIME_CAPTION},
            "snapshot": {"banner": banner, "stale": stale},
            "example_query": EXAMPLE_QUERY,
            "guided_stories": [
                {"label": label, "question": question} for label, question in GUIDED_STORIES
            ],
            "capabilities": [
                {"description": description, "examples": list(examples)}
                for description, examples in CAPABILITIES
            ],
            "metric_groups": [
                {"title": title, "names": list(names)} for title, names in metric_groups()
            ],
            "max_message_chars": MAX_MESSAGE_CHARS,
        }

    @app.post("/api/threads", status_code=201)
    def create_thread(
        body: CreateThreadRequest | None = None,
    ) -> dict[str, str | None]:
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
        store.purge_expired(now=datetime.now(UTC), ttl_seconds=resolved.thread_ttl_seconds)
        return thread_view(store, _valid_thread_id(thread_id), resolved)

    @app.delete("/api/threads/{thread_id}", status_code=204)
    def delete_thread(thread_id: str) -> Response:
        valid = _valid_thread_id(thread_id)
        if thread_lock(valid).locked():
            raise HTTPException(status_code=409, detail=TURN_IN_FLIGHT_MESSAGE)
        store.clear(valid)
        return Response(status_code=204)

    @app.post("/api/threads/{thread_id}/turns")
    async def post_turn(thread_id: str, body: TurnRequest) -> StreamingResponse:
        valid = _valid_thread_id(thread_id)
        message = body.message.strip()
        if not message:
            raise HTTPException(status_code=422, detail="Ask a question.")
        lock = thread_lock(valid)
        if not lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail=TURN_IN_FLIGHT_MESSAGE)

        loop = asyncio.get_running_loop()
        events: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

        def emit(event: str, data: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(events.put_nowait, (event, data))

        def work() -> None:
            reserved = False
            budget = SessionBudget.from_counts(
                turns=0,
                live_sec_requests=0,
                max_turns=resolved.max_turns_per_thread,
                max_live_sec_requests=resolved.max_live_sec_requests_per_thread,
            )
            try:
                prior = store.load(valid, ttl_seconds=resolved.thread_ttl_seconds)
                budget = SessionBudget.from_counts(
                    turns=prior.turn_count if prior is not None else 0,
                    live_sec_requests=prior.live_sec_requests if prior is not None else 0,
                    max_turns=resolved.max_turns_per_thread,
                    max_live_sec_requests=resolved.max_live_sec_requests_per_thread,
                )
                budget.consume_turn()
                reserved = True
                bound = prior.runtime if prior is not None else None
                run_conversation_turn(
                    valid,
                    message,
                    runtime_for(
                        bound or default_runtime_kind(resolved),
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
                emit("error", {"message": public_error_message(exc)})
            except Exception as exc:
                _LOGGER.exception("api_turn_failed")
                if reserved:
                    persist_session_budget(store, valid, budget)
                emit("error", {"message": public_error_message(exc)})
            else:
                persist_session_budget(store, valid, budget)
                emit("thread", thread_view(store, valid, resolved))
            finally:
                lock.release()

        worker = threading.Thread(target=work, name=f"turn-{valid}", daemon=True)
        worker.start()

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
