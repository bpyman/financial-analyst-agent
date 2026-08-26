"""Durable local store for conversation threads.

Swappable later for a server-backed store without changing the conversation seam.
No database server is required.

Thread state holds evidence *references*; bodies live in a per-thread
EvidenceStore so checkpoints stay small and threads do not share evidence.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote

from pydantic import BaseModel

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


class ThreadState(BaseModel):
    """Persisted conversation-thread state (not run state, not evidence bodies)."""

    thread_id: str
    messages: tuple[ThreadMessage, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    last_result_ref: str | None = None
    analysis_spec: AnalysisSpec | None = None
    pending_clarification: PendingClarification | None = None


class ThreadStore(Protocol):
    def evidence_for(self, thread_id: str) -> EvidenceStore: ...

    def load(self, thread_id: str) -> ThreadState | None: ...

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

    def load(self, thread_id: str) -> ThreadState | None:
        path = self._path(thread_id)
        if not path.is_file():
            return None
        return ThreadState.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, state: ThreadState) -> None:
        path = self._path(state.thread_id)
        path.write_text(state.model_dump_json(), encoding="utf-8")

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

    def load(self, thread_id: str) -> ThreadState | None:
        return self._states.get(thread_id)

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
