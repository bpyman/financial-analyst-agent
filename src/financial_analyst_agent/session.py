"""Visitor session identity, quotas, and snapshot freeze copy."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from financial_analyst_agent.domain.errors import SessionQuotaError
from financial_analyst_agent.presentation import format_datetime_utc, try_parse_datetime


def new_thread_id() -> str:
    return str(uuid.uuid4())


class SessionBudget:
    """Per-thread caps for public demo spend."""

    def __init__(self, *, max_turns: int, max_live_sec_requests: int) -> None:
        self.max_turns = max_turns
        self.max_live_sec_requests = max_live_sec_requests
        self.turns = 0
        self.live_sec_requests = 0

    @classmethod
    def from_counts(
        cls,
        *,
        turns: int,
        live_sec_requests: int,
        max_turns: int,
        max_live_sec_requests: int,
    ) -> SessionBudget:
        budget = cls(max_turns=max_turns, max_live_sec_requests=max_live_sec_requests)
        budget.turns = turns
        budget.live_sec_requests = live_sec_requests
        return budget

    def consume_turn(self) -> None:
        if self.turns >= self.max_turns:
            raise SessionQuotaError(
                "This session has reached its turn limit. Start over to continue."
            )
        self.turns += 1

    def consume_live_sec(self) -> None:
        if self.live_sec_requests >= self.max_live_sec_requests:
            raise SessionQuotaError(
                "This session has reached its live SEC request limit. "
                "Retry later or use recorded demo data."
            )
        self.live_sec_requests += 1


def snapshot_status(
    as_of: str,
    *,
    now: datetime | None = None,
    stale_after_days: int = 30,
) -> tuple[str, bool]:
    """Human freeze date plus whether the ranking snapshot is older than the threshold."""
    parsed = try_parse_datetime(as_of)
    clock = now or datetime.now(UTC)
    if parsed is None:
        return (f"Universe snapshot as of {as_of}", False)
    aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    stale = clock - aware >= timedelta(days=stale_after_days)
    banner = f"Universe snapshot as of {format_datetime_utc(aware)}"
    if stale:
        banner = f"{banner} — freeze is older than {stale_after_days} days"
    return banner, stale
