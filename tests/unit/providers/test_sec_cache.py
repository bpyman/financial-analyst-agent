"""Disk cache for live SEC JSON so repeat visitors do not re-hit EDGAR."""

from pathlib import Path
from typing import Any

import pytest

from financial_analyst_agent.domain.errors import SessionQuotaError
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.session import SessionBudget


class _CountingSource:
    def __init__(
        self,
        tickers: dict[str, Any],
        submissions: dict[str, Any],
        facts: dict[str, Any],
    ) -> None:
        self.tickers = tickers
        self.submissions = submissions
        self.facts = facts
        self.calls: list[str] = []

    def get_company_tickers(self) -> dict[str, Any]:
        self.calls.append("tickers")
        return self.tickers

    def get_submissions(self, cik: str) -> dict[str, Any]:
        self.calls.append(f"submissions:{cik}")
        return self.submissions

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        self.calls.append(f"facts:{cik}")
        return self.facts

    def close(self) -> None:
        return None


def test_second_lookup_reads_cache_without_inner_call(tmp_path: Path) -> None:
    inner = _CountingSource({"0": {"cik_str": "0000789019"}}, {"cik": 789019}, {"cik": 789019})
    cached = CachingSECDataSource(inner, tmp_path)
    assert cached.get_company_tickers()["0"]["cik_str"] == "0000789019"
    assert cached.get_submissions("0000789019")["cik"] == 789019
    assert cached.get_company_facts("0000789019")["cik"] == 789019
    second = CachingSECDataSource(_CountingSource({}, {}, {}), tmp_path)
    assert second.get_company_tickers()["0"]["cik_str"] == "0000789019"
    assert second.get_submissions("0000789019")["cik"] == 789019
    assert second.get_company_facts("0000789019")["cik"] == 789019
    assert inner.calls == ["tickers", "submissions:0000789019", "facts:0000789019"]


def test_cache_miss_consumes_live_sec_quota(tmp_path: Path) -> None:
    inner = _CountingSource({"ok": True}, {"cik": 1}, {"cik": 1})
    budget = SessionBudget(max_turns=10, max_live_sec_requests=1)
    cached = CachingSECDataSource(inner, tmp_path, budget=budget)
    cached.get_company_tickers()
    hit = CachingSECDataSource(
        _CountingSource({"miss": True}, {}, {}),
        tmp_path,
        budget=SessionBudget(max_turns=10, max_live_sec_requests=0),
    )
    assert hit.get_company_tickers()["ok"] is True
    with pytest.raises(SessionQuotaError):
        CachingSECDataSource(inner, tmp_path / "other", budget=budget).get_company_tickers()
