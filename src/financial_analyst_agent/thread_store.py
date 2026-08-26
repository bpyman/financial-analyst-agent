"""Durable local store for conversation threads.

Swappable later for a server-backed store without changing the conversation seam.
No database server is required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote

from pydantic import BaseModel

from financial_analyst_agent.contracts import TurnResult
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec


class ThreadMessage(BaseModel):
    role: Literal["analyst"]
    content: str


class ThreadState(BaseModel):
    """Persisted conversation-thread state (not run state)."""

    thread_id: str
    messages: tuple[ThreadMessage, ...] = ()
    results: tuple[TurnResult, ...] = ()
    last_result: TurnResult | None = None
    analysis_spec: AnalysisSpec | None = None


class ThreadStore(Protocol):
    def load(self, thread_id: str) -> ThreadState | None: ...

    def save(self, state: ThreadState) -> None: ...


class LocalThreadStore:
    """JSON files under a directory, keyed by thread identifier."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, thread_id: str) -> Path:
        return self._root / f"{quote(thread_id, safe='')}.json"

    def load(self, thread_id: str) -> ThreadState | None:
        path = self._path(thread_id)
        if not path.is_file():
            return None
        return ThreadState.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, state: ThreadState) -> None:
        path = self._path(state.thread_id)
        path.write_text(state.model_dump_json(), encoding="utf-8")


class EphemeralThreadStore:
    """In-process store for single-message compatibility threads."""

    def __init__(self) -> None:
        self._states: dict[str, ThreadState] = {}

    def load(self, thread_id: str) -> ThreadState | None:
        return self._states.get(thread_id)

    def save(self, state: ThreadState) -> None:
        self._states[state.thread_id] = state
