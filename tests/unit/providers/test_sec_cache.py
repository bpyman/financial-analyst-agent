"""Disk cache for live SEC JSON so repeat visitors do not re-hit EDGAR."""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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


@pytest.fixture(
    params=[
        ("get_company_tickers", (), "tickers.json"),
        ("get_submissions", ("0000789019",), "submissions-0000789019.json"),
        ("get_company_facts", ("0000789019",), "facts-0000789019.json"),
    ]
)
def json_entry(request: pytest.FixtureRequest) -> tuple[str, tuple[str, ...], str]:
    return request.param


@pytest.mark.parametrize("age", [3599, 3600, 3601])
def test_json_cache_expires_after_one_hour(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    json_entry: tuple[str, tuple[str, ...], str],
    age: int,
) -> None:
    method, args, filename = json_entry
    path = tmp_path / filename
    path.write_text(json.dumps({"version": "old"}), encoding="utf-8")
    now = time.time()
    os.utime(path, (now - age, now - age))
    clock = path.stat().st_mtime + age
    monkeypatch.setattr(time, "time", lambda: clock)
    inner = _CountingSource(*[{"version": "new"}] * 3)
    budget = SessionBudget(max_turns=10, max_live_sec_requests=1)
    cached = CachingSECDataSource(inner, tmp_path, budget=budget)

    expected = {"version": "old" if age < 3600 else "new"}
    assert getattr(cached, method)(*args) == expected
    assert budget.live_sec_requests == (0 if age < 3600 else 1)
    assert len(inner.calls) == budget.live_sec_requests
    assert json.loads(path.read_text(encoding="utf-8")) == expected
    assert getattr(cached, method)(*args) == expected
    assert budget.live_sec_requests == (0 if age < 3600 else 1)


@pytest.mark.parametrize("quota", [0, 1])
def test_expired_json_is_not_served_when_refresh_cannot_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    json_entry: tuple[str, tuple[str, ...], str],
    quota: int,
) -> None:
    method, args, filename = json_entry
    path = tmp_path / filename
    path.write_text('{"version": "old"}', encoding="utf-8")
    clock = path.stat().st_mtime + 3600
    monkeypatch.setattr(time, "time", lambda: clock)
    inner = _CountingSource({}, {}, {})
    attempts: list[tuple[str, ...]] = []

    def fail(*fetch_args: str) -> dict[str, Any]:
        attempts.append(fetch_args)
        raise RuntimeError("SEC unavailable")

    monkeypatch.setattr(inner, method, fail)
    budget = SessionBudget(max_turns=10, max_live_sec_requests=quota)
    cached = CachingSECDataSource(inner, tmp_path, budget=budget)

    with pytest.raises(SessionQuotaError if quota == 0 else RuntimeError):
        getattr(cached, method)(*args)
    assert budget.live_sec_requests == quota
    assert attempts == ([] if quota == 0 else [args])
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": "old"}


def test_accession_pinned_html_does_not_expire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = _CountingSource({}, {}, {})
    attempts: list[tuple[str, str, str]] = []

    def fetch(cik: str, accession: str, document: str) -> str:
        attempts.append((cik, accession, document))
        return "<html>filing</html>"

    monkeypatch.setattr(inner, "get_filing_document", fetch, raising=False)
    budget = SessionBudget(max_turns=10, max_live_sec_requests=1)
    cached = CachingSECDataSource(inner, tmp_path, budget=budget)
    args = ("0000789019", "0000789019-26-000001", "report.htm")
    assert cached.get_filing_document(*args) == "<html>filing</html>"
    path = next(tmp_path.iterdir())
    os.utime(path, (0, 0))
    second = CachingSECDataSource(inner, tmp_path, budget=budget)
    assert second.get_filing_document(*args) == "<html>filing</html>"
    assert budget.live_sec_requests == 1
    assert attempts == [args]


def test_concurrent_cold_fills_charge_quota_once(tmp_path: Path) -> None:
    inner = _CountingSource({"ok": True}, {}, {})
    original = inner.get_company_tickers
    started = threading.Event()

    def delayed() -> dict[str, Any]:
        started.set()
        time.sleep(0.05)
        return original()

    inner.get_company_tickers = delayed  # type: ignore[method-assign]
    budget = SessionBudget(max_turns=10, max_live_sec_requests=12)
    cached = CachingSECDataSource(inner, tmp_path, budget=budget)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(cached.get_company_tickers) for _ in range(8)]
        assert started.wait(timeout=2)
        results = [future.result() for future in futures]
    assert results == [{"ok": True}] * 8
    assert inner.calls == ["tickers"]
    assert budget.live_sec_requests == 1
