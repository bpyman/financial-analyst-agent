"""Durable local store for conversation threads.

Swappable later for a server-backed store without changing the conversation seam.
No database server is required.

Thread state holds evidence *references*; bodies live in a per-thread
EvidenceStore so checkpoints stay small and threads do not share evidence.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote

from pydantic import BaseModel, Field

from financial_analyst_agent.contracts import Intent, RuntimeKind, TurnResult
from financial_analyst_agent.evidence_store import (
    EvidenceStore,
    InMemoryEvidenceStore,
    LocalEvidenceStore,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch


class ThreadMessage(BaseModel):
    role: Literal["analyst"]
    content: str


class PendingClarification(BaseModel):
    """Analysis held awaiting the analyst's answer. Nothing has been fetched."""

    kind: Literal["ambiguous_metric", "ambiguous_mode"]
    candidates: tuple[str, ...]
    patch: SpecPatch
    intent: Intent = Intent.LOOKUP
    metric_role: Literal["add", "remove"] = "add"
    # The question that was held, so an answer like "replace" resumes it rather
    # than being read as a question of its own. Empty in threads saved before.
    question: str = ""


class ThreadState(BaseModel):
    """Persisted conversation-thread state (not run state, not evidence bodies).

    ``runtime`` is the runtime the thread is bound to. ``None`` means not yet bound:
    a thread saved before binding existed binds on its next turn.
    """

    thread_id: str
    runtime: RuntimeKind | None = None
    messages: tuple[ThreadMessage, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    last_result_ref: str | None = None
    analysis_spec: AnalysisSpec | None = None
    pending_clarification: PendingClarification | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    turn_count: int = 0
    live_sec_requests: int = 0


class ThreadStore(Protocol):
    def evidence_for(self, thread_id: str) -> EvidenceStore: ...

    def load(
        self,
        thread_id: str,
        *,
        now: datetime | None = None,
        ttl_seconds: int | None = None,
    ) -> ThreadState | None: ...

    def save(self, state: ThreadState) -> None: ...

    def resolve_results(self, state: ThreadState) -> tuple[TurnResult, ...]: ...

    def resolve_last_result(self, state: ThreadState) -> TurnResult | None: ...

    def clear(self, thread_id: str) -> None: ...


# A checkpoint dated this far ahead of the clock was not written by it.
_CLOCK_SKEW = timedelta(minutes=5)
# Thread ids name files: letters, digits, "-" and "_" only, so ".." names none.
_THREAD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def _expired(state: ThreadState, now: datetime, ttl_seconds: int) -> bool:
    updated = state.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    if updated - now > _CLOCK_SKEW:
        # A future date would otherwise never expire.
        return True
    return now - updated >= timedelta(seconds=ttl_seconds)


def _checked_id(thread_id: str) -> str:
    if not _THREAD_ID.fullmatch(thread_id):
        raise ValueError("A thread id is 1 to 128 letters, digits, '-' or '_'")
    return thread_id


class LocalThreadStore:
    """JSON thread checkpoints plus a per-thread evidence directory.

    Loads, saves, clears, and expiry share one lock. Expiry re-reads the
    checkpoint and asks ``keep`` (a turn in flight) while holding it, so it
    never deletes a checkpoint saved after it decided, and a turn that starts
    meanwhile reads its thread only once the expiry is done: none of the
    turn's evidence is removed from under it. One store per process.
    """

    def __init__(self, root: Path) -> None:
        self._lock = threading.RLock()
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._evidence_root = root / "evidence"
        self._evidence_root.mkdir(parents=True, exist_ok=True)

    def evidence_for(self, thread_id: str) -> EvidenceStore:
        return LocalEvidenceStore(self._evidence_dir(thread_id))

    def _path(self, thread_id: str) -> Path:
        return self._root / f"{quote(_checked_id(thread_id), safe='')}.json"

    def _evidence_dir(self, thread_id: str) -> Path:
        return self._evidence_root / quote(_checked_id(thread_id), safe="")

    def load(
        self,
        thread_id: str,
        *,
        now: datetime | None = None,
        ttl_seconds: int | None = None,
        keep: Callable[[str], bool] = lambda _thread_id: False,
    ) -> ThreadState | None:
        """The thread, or ``None``; past the TTL it is cleared unless ``keep`` names it.

        A caller that holds the thread's turn lock leaves ``keep`` alone: it is
        the one that may expire the thread.
        """
        with self._lock:
            state = self._read(self._path(thread_id))
            if state is None or ttl_seconds is None:
                return state
            if _expired(state, now or datetime.now(UTC), ttl_seconds) and not keep(thread_id):
                self._clear(thread_id)
                return None
            return state

    @staticmethod
    def _read(path: Path) -> ThreadState | None:
        """The checkpoint at ``path``; a missing or unreadable file reads as no thread."""
        try:
            return ThreadState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self, state: ThreadState) -> None:
        """Write the whole checkpoint or nothing: readers never see a torn file."""
        path = self._path(state.thread_id)
        handle, temp_name = tempfile.mkstemp(dir=self._root, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as temp:
                temp.write(state.model_dump_json())
            with self._lock:
                os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def purge_expired(
        self,
        *,
        now: datetime,
        ttl_seconds: int,
        keep: Callable[[str], bool] = lambda _thread_id: False,
    ) -> int:
        """Clear threads idle past the TTL, except those ``keep`` names (a turn in flight)."""
        removed = 0
        for path in self._root.glob("*.json"):
            # A first read without the lock skips the fresh threads cheaply;
            # an expired one is read again, and kept or cleared, under it.
            state = self._read(path)
            if state is None or not _expired(state, now, ttl_seconds):
                continue
            with self._lock:
                state = self._read(path)
                if state is None or keep(state.thread_id):
                    continue
                if _expired(state, now, ttl_seconds):
                    self._clear(state.thread_id)
                    removed += 1
        return removed

    def resolve_results(self, state: ThreadState) -> tuple[TurnResult, ...]:
        evidence = self.evidence_for(state.thread_id)
        results: list[TurnResult] = []
        for ref in state.evidence_refs:
            if ref.startswith("result-"):
                try:
                    results.append(evidence.get_result(ref))
                except (KeyError, OSError, ValueError):
                    # A gone or damaged answer is left out; the rest still show.
                    continue
        return tuple(results)

    def resolve_last_result(self, state: ThreadState) -> TurnResult | None:
        if state.last_result_ref is None:
            return None
        try:
            return self.evidence_for(state.thread_id).get_result(state.last_result_ref)
        except (KeyError, OSError, ValueError):
            return None

    def clear(self, thread_id: str) -> None:
        with self._lock:
            self._clear(thread_id)

    def _clear(self, thread_id: str) -> None:
        path = self._path(thread_id)
        if path.is_file():
            path.unlink()
        evidence_dir = self._evidence_dir(thread_id)
        if evidence_dir.is_dir():
            shutil.rmtree(evidence_dir)


class EphemeralThreadStore:
    """In-process store for single-message compatibility threads."""

    def __init__(self) -> None:
        self._states: dict[str, ThreadState] = {}
        self._evidence: dict[str, InMemoryEvidenceStore] = {}

    def evidence_for(self, thread_id: str) -> EvidenceStore:
        if thread_id not in self._evidence:
            self._evidence[thread_id] = InMemoryEvidenceStore()
        return self._evidence[thread_id]

    def load(
        self,
        thread_id: str,
        *,
        now: datetime | None = None,
        ttl_seconds: int | None = None,
    ) -> ThreadState | None:
        state = self._states.get(thread_id)
        if state is None or ttl_seconds is None:
            return state
        clock = now or datetime.now(UTC)
        updated = state.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        if clock - updated >= timedelta(seconds=ttl_seconds):
            self.clear(thread_id)
            return None
        return state

    def save(self, state: ThreadState) -> None:
        self._states[state.thread_id] = state

    def resolve_results(self, state: ThreadState) -> tuple[TurnResult, ...]:
        evidence = self.evidence_for(state.thread_id)
        results: list[TurnResult] = []
        for ref in state.evidence_refs:
            if ref.startswith("result-"):
                try:
                    results.append(evidence.get_result(ref))
                except (KeyError, OSError, ValueError):
                    # A gone or damaged answer is left out; the rest still show.
                    continue
        return tuple(results)

    def resolve_last_result(self, state: ThreadState) -> TurnResult | None:
        if state.last_result_ref is None:
            return None
        try:
            return self.evidence_for(state.thread_id).get_result(state.last_result_ref)
        except (KeyError, OSError, ValueError):
            return None

    def clear(self, thread_id: str) -> None:
        self._states.pop(thread_id, None)
        self._evidence.pop(thread_id, None)
