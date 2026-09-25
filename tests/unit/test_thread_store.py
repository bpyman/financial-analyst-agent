"""LocalThreadStore durability: atomic saves, unreadable files, purge that spares busy threads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from financial_analyst_agent import thread_store
from financial_analyst_agent.thread_store import LocalThreadStore, ThreadMessage, ThreadState

LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)
LATER = LONG_AGO + timedelta(days=1)


def test_a_failed_save_leaves_the_previous_checkpoint_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalThreadStore(tmp_path)
    first = ThreadState(thread_id="t", messages=(ThreadMessage(role="analyst", content="q1"),))
    store.save(first)

    def crash(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(thread_store.os, "replace", crash)
    second = first.model_copy(update={"turn_count": 2})
    with pytest.raises(OSError):
        store.save(second)

    assert store.load("t") == first
    assert sorted(path.name for path in tmp_path.iterdir()) == ["evidence", "t.json"]


def test_an_unreadable_thread_file_reads_as_missing(tmp_path: Path) -> None:
    store = LocalThreadStore(tmp_path)
    (tmp_path / "torn.json").write_text('{"thread_id": "torn", "mess', encoding="utf-8")

    assert store.load("torn") is None
    assert store.load("torn", ttl_seconds=60) is None


def test_purge_spares_threads_the_caller_keeps(tmp_path: Path) -> None:
    store = LocalThreadStore(tmp_path)
    for thread_id in ("busy", "idle"):
        store.save(ThreadState(thread_id=thread_id, updated_at=LONG_AGO))

    removed = store.purge_expired(now=LATER, ttl_seconds=60, keep=lambda tid: tid == "busy")

    assert removed == 1
    assert store.load("busy") is not None
    assert store.load("idle") is None
