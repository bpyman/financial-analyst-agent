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

# Long enough to be a filing: the cache keeps nothing shorter.
FILING = "<html><body>" + "Item 2. Management's Discussion and Analysis. " * 300 + "</body></html>"


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
        return FILING

    monkeypatch.setattr(inner, "get_filing_document", fetch, raising=False)
    budget = SessionBudget(max_turns=10, max_live_sec_requests=1)
    cached = CachingSECDataSource(inner, tmp_path, budget=budget)
    args = ("0000789019", "0000789019-26-000001", "report.htm")
    assert cached.get_filing_document(*args) == FILING
    path = next(tmp_path.iterdir())
    os.utime(path, (0, 0))
    second = CachingSECDataSource(inner, tmp_path, budget=budget)
    assert second.get_filing_document(*args) == FILING
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


def test_concurrent_fills_across_cache_instances_share_one_fetch(tmp_path: Path) -> None:
    inner = _CountingSource({"ok": True}, {}, {})
    original = inner.get_company_tickers
    started = threading.Event()

    def delayed() -> dict[str, Any]:
        started.set()
        time.sleep(0.05)
        return original()

    inner.get_company_tickers = delayed  # type: ignore[method-assign]
    left = CachingSECDataSource(
        inner, tmp_path, budget=SessionBudget(max_turns=10, max_live_sec_requests=12)
    )
    right = CachingSECDataSource(
        inner, tmp_path, budget=SessionBudget(max_turns=10, max_live_sec_requests=12)
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit((left if index % 2 == 0 else right).get_company_tickers)
            for index in range(8)
        ]
        assert started.wait(timeout=2)
        results = [future.result() for future in futures]
    assert results == [{"ok": True}] * 8
    assert inner.calls == ["tickers"]
    assert left._budget is not None
    assert right._budget is not None
    assert left._budget.live_sec_requests + right._budget.live_sec_requests == 1
    assert json.loads((tmp_path / "tickers.json").read_text(encoding="utf-8")) == {"ok": True}


def test_missing_company_facts_are_remembered(tmp_path: Path) -> None:
    from financial_analyst_agent.domain.errors import ProviderError

    class _Missing(_CountingSource):
        def get_company_facts(self, cik: str) -> dict[str, Any]:
            self.calls.append(f"facts:{cik}")
            raise ProviderError("not found", details={"status_code": 404})

    inner = _Missing({}, {}, {})
    budget = SessionBudget(max_turns=10, max_live_sec_requests=10)
    for _ in range(2):
        with pytest.raises(ProviderError) as caught:
            CachingSECDataSource(inner, tmp_path, budget=budget).get_company_facts("0000000001")
        assert caught.value.details["status_code"] == 404

    assert inner.calls == ["facts:0000000001"]


class _PagedSource(_CountingSource):
    """A source whose submissions keep older 10-Qs in numbered pages."""

    def __init__(self, pages: dict[str, Any]) -> None:
        recent = {
            "form": ["10-Q"],
            "accessionNumber": ["0000019617-26-000800"],
            "reportDate": ["2026-06-30"],
        }
        files = [{"name": name} for name in pages]
        super().__init__({}, {"filings": {"recent": recent, "files": files}}, {})
        self.pages = pages

    def get_submissions(self, cik: str, *, with_history: bool = True) -> dict[str, Any]:
        assert with_history is False
        return json.loads(json.dumps(super().get_submissions(cik)))

    def get_submissions_page(self, name: str) -> dict[str, Any]:
        self.calls.append(f"page:{name}")
        page = self.pages[name]
        if isinstance(page, Exception):
            raise page
        return page


def _page(report_date: str) -> dict[str, Any]:
    return {
        "form": ["10-Q"],
        "accessionNumber": [f"0000019617-{report_date[2:4]}-000100"],
        "reportDate": [report_date],
    }


def test_each_older_submissions_page_is_cached_and_charged(tmp_path: Path) -> None:
    inner = _PagedSource(
        {
            "CIK0000019617-submissions-001.json": _page("2025-06-30"),
            "CIK0000019617-submissions-002.json": _page("2023-06-30"),
        }
    )
    budget = SessionBudget(max_turns=10, max_live_sec_requests=5)
    cached = CachingSECDataSource(inner, tmp_path, budget=budget)

    recent = cached.get_submissions("0000019617")["filings"]["recent"]
    again = cached.get_submissions("0000019617")["filings"]["recent"]

    assert recent["reportDate"] == ["2026-06-30", "2025-06-30", "2023-06-30"]
    assert again == recent
    assert budget.live_sec_requests == 3
    assert len(inner.calls) == 3


def test_older_pages_that_fail_or_exceed_the_budget_leave_recent_filings(
    tmp_path: Path,
) -> None:
    from financial_analyst_agent.domain.errors import ProviderError

    failing = _PagedSource(
        {"CIK0000019617-submissions-001.json": ProviderError("timeout", details={})}
    )
    recent = CachingSECDataSource(failing, tmp_path / "a").get_submissions("0000019617")
    assert recent["filings"]["recent"]["reportDate"] == ["2026-06-30"]

    spent = _PagedSource({"CIK0000019617-submissions-001.json": _page("2025-06-30")})
    budget = SessionBudget(max_turns=10, max_live_sec_requests=1)
    cached = CachingSECDataSource(spent, tmp_path / "b", budget=budget)
    assert cached.get_submissions("0000019617")["filings"]["recent"]["reportDate"] == [
        "2026-06-30"
    ]
    assert spent.calls == ["submissions:0000019617"]


@pytest.mark.parametrize("damage", ['{"cik": 7', "", "\udcff"])
def test_a_damaged_cache_file_is_refetched(tmp_path: Path, damage: str) -> None:
    path = tmp_path / "submissions-0000789019.json"
    path.write_bytes(damage.encode("utf-8", "surrogateescape"))
    inner = _CountingSource({}, {"cik": 789019}, {})

    payload = CachingSECDataSource(inner, tmp_path).get_submissions("0000789019")

    assert payload == {"cik": 789019}
    assert inner.calls == ["submissions:0000789019"]
    assert json.loads(path.read_text(encoding="utf-8")) == {"cik": 789019}


class _FilingSource(_CountingSource):
    def __init__(self, document: str) -> None:
        super().__init__({}, {}, {})
        self.document = document

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        self.calls.append(f"html:{document}")
        return self.document


FILING_ARGS = ("0000789019", "0000789019-26-000001", "report.htm")


@pytest.mark.parametrize(
    "reply",
    ["", "<html><body>Service Unavailable</body></html>", "x" * 20_000],
    ids=["empty", "error page", "not html"],
)
def test_an_empty_or_error_page_is_never_cached_as_a_filing(tmp_path: Path, reply: str) -> None:
    from financial_analyst_agent.domain.errors import ProviderError

    inner = _FilingSource(reply)
    cached = CachingSECDataSource(inner, tmp_path)
    for _ in range(2):
        with pytest.raises(ProviderError, match="no usable filing document"):
            cached.get_filing_document(*FILING_ARGS)

    assert inner.calls == ["html:report.htm"] * 2
    assert list(tmp_path.iterdir()) == []


def test_a_tiny_cached_filing_is_fetched_again(tmp_path: Path) -> None:
    path = tmp_path / "html-0000789019-0000789019-26-000001-report.htm"
    path.write_text("<html><body>Maintenance</body></html>", encoding="utf-8")
    inner = _FilingSource(FILING)

    assert CachingSECDataSource(inner, tmp_path).get_filing_document(*FILING_ARGS) == FILING
    assert inner.calls == ["html:report.htm"]
    assert path.read_text(encoding="utf-8") == FILING


def test_a_cached_json_of_the_wrong_shape_is_fetched_again(tmp_path: Path) -> None:
    (tmp_path / "tickers.json").write_text("[1, 2, 3]", encoding="utf-8")
    inner = _CountingSource({"ok": True}, {}, {})

    assert CachingSECDataSource(inner, tmp_path).get_company_tickers() == {"ok": True}
    assert inner.calls == ["tickers"]


def test_a_full_disk_costs_the_cache_not_the_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_analyst_agent.providers.sec import cache

    def full(*_args: Any) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(cache.os, "replace", full)
    inner = _CountingSource({"ok": True}, {}, {"cik": 789019, "facts": {}})
    cached = CachingSECDataSource(inner, tmp_path)

    assert cached.get_company_tickers() == {"ok": True}
    assert cached.get_company_facts("0000789019") == {"cik": 789019, "facts": {}}
    assert list(tmp_path.iterdir()) == []


def test_a_cache_directory_that_cannot_be_made_still_answers(tmp_path: Path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("", encoding="utf-8")
    inner = _CountingSource({"ok": True}, {}, {})

    assert CachingSECDataSource(inner, blocked / "sec").get_company_tickers() == {"ok": True}


def test_a_fill_does_not_wait_forever_for_another_fetch(tmp_path: Path) -> None:
    from financial_analyst_agent.domain.errors import ProviderError
    from financial_analyst_agent.providers.sec.cache import _lock_for

    lock = _lock_for(tmp_path / "tickers.json")
    lock.acquire()
    try:
        cached = CachingSECDataSource(
            _CountingSource({"ok": True}, {}, {}), tmp_path, fill_wait_seconds=0.05
        )
        started = time.monotonic()
        with pytest.raises(ProviderError, match="still fetching"):
            cached.get_company_tickers()
        assert time.monotonic() - started < 1
    finally:
        lock.release()


def test_a_sweep_removes_the_oldest_files_past_the_budget(tmp_path: Path) -> None:
    from financial_analyst_agent.providers.sec.cache import sweep_cache

    now = time.time()
    for index in range(5):
        path = tmp_path / f"html-{index}"
        path.write_bytes(b"x" * 1024 * 1024)
        os.utime(path, (now - 1000 + index, now - 1000 + index))
    stale = tmp_path / ".tickers.json.abc.tmp"
    stale.write_bytes(b"{")
    os.utime(stale, (now - 7200, now - 7200))
    (tmp_path / ".tickers.json.def.tmp").write_bytes(b"{")

    removed = sweep_cache(tmp_path, 3 * 1024 * 1024, now=now)

    assert removed == 4
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        ".tickers.json.def.tmp",
        "html-3",
        "html-4",
    ]
