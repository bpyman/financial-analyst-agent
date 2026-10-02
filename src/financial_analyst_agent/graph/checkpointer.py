"""The analysis graph's checkpointer: one thread's latest checkpoint, kept in its thread record.

ADR 0005: an ambiguous metric is an ``interrupt`` holding a pending analysis.
LangGraph writes the paused run through this ``BaseCheckpointSaver``; the
conversation seam then stores ``record()`` in the thread record, and the next
turn restores it, in this process or after a restart, so ``Command(resume=...)``
picks up the same held analysis.

Why the thread record rather than a separate checkpoint database: the app runs
one process with a file-backed thread store (render.yaml ``numInstances: 1``).
Keeping the checkpoint in the same file means one atomic write (temp file and
``os.replace``) commits the thread and its paused run together, an unreadable
file reads as no thread at all, Start over and expiry remove both at once, and
a turn the API abandoned can write neither. Nothing new to migrate or purge.

The app never replays or forks history, so each namespace keeps only its
latest checkpoint and that checkpoint's pending writes (the interrupt). The
saver serves exactly one thread, and refuses a config naming another.
Deserialization is limited to the graph's own state models (no arbitrary
imports from a tampered file).
"""

from __future__ import annotations

import base64
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.serde.types import INTERRUPT
from pydantic import BaseModel

from financial_analyst_agent.contracts import Intent, RendererKind
from financial_analyst_agent.graph.state import CHECKPOINTED_TYPES

_ENUMS: tuple[type[Enum], ...] = (Intent, RendererKind)
SERDE = JsonPlusSerializer(allowed_msgpack_modules=(*CHECKPOINTED_TYPES, *_ENUMS))


class SerializedValue(BaseModel):
    """One ``serde.dumps_typed`` value: its format and its bytes, base64-encoded."""

    type: str
    data: str

    @classmethod
    def of(cls, typed: tuple[str, bytes]) -> SerializedValue:
        return cls(type=typed[0], data=base64.b64encode(typed[1]).decode("ascii"))

    def typed(self) -> tuple[str, bytes]:
        return self.type, base64.b64decode(self.data)


class SavedWrite(BaseModel):
    task_id: str
    index: int
    channel: str
    value: SerializedValue
    task_path: str = ""


class SavedCheckpoint(BaseModel):
    """A namespace's latest checkpoint and the writes pending on it."""

    namespace: str = ""
    checkpoint_id: str
    parent_id: str | None = None
    checkpoint: SerializedValue
    metadata: SerializedValue
    writes: tuple[SavedWrite, ...] = ()


class GraphCheckpoint(BaseModel):
    """What a thread record stores while the analysis graph is paused."""

    saved: tuple[SavedCheckpoint, ...]


@dataclass
class _Slot:
    checkpoint_id: str
    parent_id: str | None
    checkpoint: tuple[str, bytes]
    metadata: tuple[str, bytes]
    # (task id, write index) → (channel, value, task path)
    writes: dict[tuple[str, int], tuple[str, tuple[str, bytes], str]] = field(
        default_factory=dict
    )

    @classmethod
    def restore(cls, saved: SavedCheckpoint) -> _Slot:
        return cls(
            checkpoint_id=saved.checkpoint_id,
            parent_id=saved.parent_id,
            checkpoint=saved.checkpoint.typed(),
            metadata=saved.metadata.typed(),
            writes={
                (write.task_id, write.index): (
                    write.channel,
                    write.value.typed(),
                    write.task_path,
                )
                for write in saved.writes
            },
        )

    def saved(self, namespace: str) -> SavedCheckpoint:
        return SavedCheckpoint(
            namespace=namespace,
            checkpoint_id=self.checkpoint_id,
            parent_id=self.parent_id,
            checkpoint=SerializedValue.of(self.checkpoint),
            metadata=SerializedValue.of(self.metadata),
            writes=tuple(
                SavedWrite(
                    task_id=task_id,
                    index=index,
                    channel=channel,
                    value=SerializedValue.of(value),
                    task_path=task_path,
                )
                for (task_id, index), (channel, value, task_path) in self.writes.items()
            ),
        )


class ThreadCheckpointer(BaseCheckpointSaver[int]):
    """Latest-checkpoint-only saver for one conversation thread, restored from its record."""

    def __init__(self, thread_id: str, record: GraphCheckpoint | None = None) -> None:
        super().__init__(serde=SERDE)
        self._thread_id = thread_id
        self._lock = threading.Lock()
        self._slots: dict[str, _Slot] = (
            {saved.namespace: _Slot.restore(saved) for saved in record.saved} if record else {}
        )

    def record(self) -> GraphCheckpoint | None:
        """The checkpoints to store in the thread record, or None when there are none."""
        with self._lock:
            if not self._slots:
                return None
            return GraphCheckpoint(
                saved=tuple(slot.saved(namespace) for namespace, slot in self._slots.items())
            )

    def _namespace(self, config: RunnableConfig) -> str:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if thread_id != self._thread_id:
            raise ValueError(
                f"this checkpointer holds thread {self._thread_id!r}, not {thread_id!r}"
            )
        return str(configurable.get("checkpoint_ns", ""))

    def _tuple(self, namespace: str, slot: _Slot) -> CheckpointTuple:
        def at(checkpoint_id: str) -> RunnableConfig:
            return {
                "configurable": {
                    "thread_id": self._thread_id,
                    "checkpoint_ns": namespace,
                    "checkpoint_id": checkpoint_id,
                }
            }

        checkpoint: Checkpoint = self.serde.loads_typed(slot.checkpoint)
        metadata: CheckpointMetadata = self.serde.loads_typed(slot.metadata)
        return CheckpointTuple(
            config=at(slot.checkpoint_id),
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=at(slot.parent_id) if slot.parent_id else None,
            pending_writes=[
                (task_id, channel, self.serde.loads_typed(value))
                for (task_id, _index), (channel, value, _path) in slot.writes.items()
            ],
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        namespace = self._namespace(config)
        with self._lock:
            slot = self._slots.get(namespace)
            if slot is None:
                return None
            wanted = get_checkpoint_id(config)
            if wanted is not None and wanted != slot.checkpoint_id:
                # Only the latest checkpoint is kept: an earlier one is gone.
                return None
            return self._tuple(namespace, slot)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        wanted_namespace = self._namespace(config) if config is not None else None
        wanted_id = get_checkpoint_id(config) if config is not None else None
        before_id = get_checkpoint_id(before) if before is not None else None
        with self._lock:
            found = [
                self._tuple(namespace, slot)
                for namespace, slot in self._slots.items()
                if (wanted_namespace is None or namespace == wanted_namespace)
                and (wanted_id is None or slot.checkpoint_id == wanted_id)
                and (before_id is None or slot.checkpoint_id < before_id)
            ]
        listed = 0
        for item in found:
            if filter and any(item.metadata.get(key) != value for key, value in filter.items()):
                continue
            if limit is not None and listed >= limit:
                return
            listed += 1
            yield item

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        namespace = self._namespace(config)
        slot = _Slot(
            checkpoint_id=checkpoint["id"],
            parent_id=get_checkpoint_id(config),
            checkpoint=self.serde.dumps_typed(checkpoint),
            metadata=self.serde.dumps_typed(get_checkpoint_metadata(config, metadata)),
        )
        with self._lock:
            # The new checkpoint supersedes the namespace's last one and its writes.
            self._slots[namespace] = slot
        return {
            "configurable": {
                "thread_id": self._thread_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        namespace = self._namespace(config)
        checkpoint_id = get_checkpoint_id(config)
        with self._lock:
            slot = self._slots.get(namespace)
            if slot is None or slot.checkpoint_id != checkpoint_id:
                # Writes against a superseded checkpoint are never read again.
                return
            for index, (channel, value) in enumerate(writes):
                key = (task_id, WRITES_IDX_MAP.get(channel, index))
                if key[1] >= 0 and key in slot.writes:
                    continue
                slot.writes[key] = (channel, self.serde.dumps_typed(value), task_path)

    def delete_thread(self, thread_id: str) -> None:
        if thread_id == self._thread_id:
            with self._lock:
                self._slots.clear()


def paused_values(record: GraphCheckpoint | None) -> tuple[Any, ...]:
    """The values the root graph is paused on (``interrupt(value)``), oldest first.

    A record that cannot be decoded is paused on nothing; the next turn drops it.
    """
    if record is None:
        return ()
    values: list[Any] = []
    try:
        for saved in record.saved:
            if saved.namespace:
                continue
            for write in saved.writes:
                if write.channel != INTERRUPT:
                    continue
                interrupts = SERDE.loads_typed(write.value.typed())
                values.extend(getattr(item, "value", item) for item in interrupts)
    except Exception:
        return ()
    return tuple(values)
