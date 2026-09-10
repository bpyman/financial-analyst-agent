"""Durable local store for conversation threads.

Swappable later for a server-backed store without changing the conversation seam.
No database server is required.

Thread state holds evidence *references*; bodies live in a per-thread
EvidenceStore so checkpoints stay small and threads do not share evidence.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote

from pydantic import BaseModel, Field

from financial_analyst_agent.contracts import Intent, TurnResult
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


class ThreadState(BaseModel):
    """Persisted conversation-thread state (not run state, not evidence bodies)."""

    thread_id: str
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


class LocalThreadStore:
    """JSON thread checkpoints plus a per-thread evidence directory."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._evidence_root = root / "evidence"
        self._evidence_root.mkdir(parents=True, exist_ok=True)

    def evidence_for(self, thread_id: str) -> EvidenceStore:
        return LocalEvidenceStore(self._evidence_dir(thread_id))

    def _path(self, thread_id: str) -> Path:
        return self._root / f"{quote(thread_id, safe='')}.json"

    def _evidence_dir(self, thread_id: str) -> Path:
        return self._evidence_root / quote(thread_id, safe="")

    def load(
        self,
        thread_id: str,
        *,
        now: datetime | None = None,
        ttl_seconds: int | None = None,
    ) -> ThreadState | None:
        path = self._path(thread_id)
        if not path.is_file():
            return None
        state = ThreadState.model_validate_json(path.read_text(encoding="utf-8"))
        if ttl_seconds is None:
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
        path = self._path(state.thread_id)
        path.write_text(state.model_dump_json(), encoding="utf-8")

    def purge_expired(self, *, now: datetime, ttl_seconds: int) -> int:
        removed = 0
        for path in self._root.glob("*.json"):
            try:
                state = ThreadState.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            updated = state.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if now - updated >= timedelta(seconds=ttl_seconds):
                self.clear(state.thread_id)
                removed += 1
        return removed

    def resolve_results(self, state: ThreadState) -> tuple[TurnResult, ...]:
        evidence = self.evidence_for(state.thread_id)
        results: list[TurnResult] = []
        for ref in state.evidence_refs:
            if ref.startswith("result-"):
                results.append(evidence.get_result(ref))
        return tuple(results)

    def resolve_last_result(self, state: ThreadState) -> TurnResult | None:
        if state.last_result_ref is None:
            return None
        return self.evidence_for(state.thread_id).get_result(state.last_result_ref)

    def clear(self, thread_id: str) -> None:
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
                results.append(evidence.get_result(ref))
        return tuple(results)

    def resolve_last_result(self, state: ThreadState) -> TurnResult | None:
        if state.last_result_ref is None:
            return None
        return self.evidence_for(state.thread_id).get_result(state.last_result_ref)

    def clear(self, thread_id: str) -> None:
        self._states.pop(thread_id, None)
        self._evidence.pop(thread_id, None)
