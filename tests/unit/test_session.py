"""Isolated, expiring conversation sessions and live-SEC quotas."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from financial_analyst_agent.domain.errors import SessionQuotaError
from financial_analyst_agent.session import (
    SessionBudget,
    new_thread_id,
    snapshot_status,
)
from financial_analyst_agent.thread_store import LocalThreadStore, ThreadState


def test_new_thread_ids_are_unique() -> None:
    first = new_thread_id()
    second = new_thread_id()
    assert first != second
    assert first != "local"
    assert second != "local"


def test_expired_thread_is_treated_as_missing(tmp_path: Path) -> None:
    store = LocalThreadStore(tmp_path)
    state = ThreadState(
        thread_id="visitor-a",
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    store.save(state)
    still_valid = store.load(
        "visitor-a",
        now=datetime(2026, 1, 1, 1, tzinfo=UTC),
        ttl_seconds=7200,
    )
    assert still_valid is not None
    assert store.load("visitor-a", now=datetime(2026, 1, 2, tzinfo=UTC), ttl_seconds=7200) is None
    assert store.load("visitor-a") is None


def test_purge_expired_removes_old_threads(tmp_path: Path) -> None:
    store = LocalThreadStore(tmp_path)
    store.save(ThreadState(thread_id="fresh", updated_at=datetime(2026, 9, 8, tzinfo=UTC)))
    store.save(ThreadState(thread_id="stale", updated_at=datetime(2026, 9, 1, tzinfo=UTC)))
    removed = store.purge_expired(
        now=datetime(2026, 9, 8, 12, tzinfo=UTC),
        ttl_seconds=3600 * 24,
    )
    assert removed == 1
    assert store.load("fresh") is not None
    assert store.load("stale") is None


def test_session_budget_caps_turns_and_live_sec() -> None:
    budget = SessionBudget(max_turns=2, max_live_sec_requests=1)
    budget.consume_turn()
    budget.consume_live_sec()
    with pytest.raises(SessionQuotaError, match="live SEC"):
        budget.consume_live_sec()
    budget.consume_turn()
    with pytest.raises(SessionQuotaError, match="turn"):
        budget.consume_turn()


def test_snapshot_status_warns_when_freeze_is_stale() -> None:
    banner, stale = snapshot_status(
        "2026-08-17T16:00:00+00:00",
        now=datetime(2026, 9, 8, tzinfo=UTC),
        stale_after_days=14,
    )
    assert "Aug 17, 2026" in banner
    assert stale is True
    fresh, still_stale = snapshot_status(
        "2026-08-17T16:00:00+00:00",
        now=datetime(2026, 8, 18, tzinfo=UTC),
        stale_after_days=30,
    )
    assert "Aug 17, 2026" in fresh
    assert still_stale is False
