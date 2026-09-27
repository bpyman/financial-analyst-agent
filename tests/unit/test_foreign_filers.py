"""Foreign private issuers (20-F/40-F filers) stay out of rankings and peers."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from financial_analyst_agent import snapshot_builder
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.providers.sec.submissions import files_quarterly_reports
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from financial_analyst_agent.snapshot_builder import annotate_filers
from financial_analyst_agent.universe import (
    UniverseCompany,
    UniverseSnapshot,
    load_universe_snapshot,
    write_universe_snapshot,
)

AS_OF = datetime(2026, 9, 26, 21, 3, 37, tzinfo=UTC)
PNC = "0000713676"
MIZUHO = "0001335730"
TRUIST = "0000092230"


def _submissions(*filings: tuple[str, str]) -> dict[str, Any]:
    return {
        "cik": "1",
        "filings": {
            "recent": {
                "form": [form for form, _filed in filings],
                "filingDate": [filed for _form, filed in filings],
            }
        },
    }


@pytest.mark.parametrize(
    ("filings", "expected"),
    [
        ((("6-K", "2026-08-01"), ("20-F", "2026-06-20")), False),
        ((("40-F", "2026-03-01"), ("6-K", "2026-02-01")), False),
        ((("10-Q", "2026-08-01"), ("10-K", "2026-02-15")), True),
        ((("10-K", "2026-03-01"), ("20-F", "2025-04-01")), True),
        ((("20-F", "2026-04-01"), ("10-K", "2025-03-01")), False),
        ((("424B2", "2026-09-01"), ("8-K", "2026-08-01")), True),
        ((("20-F/A", "2026-09-01"), ("10-Q", "2026-08-01")), True),
        ((), True),
    ],
    ids=[
        "20-F only",
        "40-F only",
        "domestic",
        "switched to 10-K",
        "switched to 20-F",
        "no periodic reports",
        "late 20-F amendment",
        "empty",
    ],
)
def test_files_quarterly_reports_follows_the_latest_periodic_report(
    filings: tuple[tuple[str, str], ...], expected: bool
) -> None:
    assert files_quarterly_reports(_submissions(*filings)) is expected


def test_files_quarterly_reports_tolerates_a_malformed_payload() -> None:
    assert files_quarterly_reports({"filings": "nope"}) is True
    assert files_quarterly_reports({"filings": {"recent": {"form": ["20-F"]}}}) is True


def _company(
    cik: str, name: str, ticker: str, cap: str, *, quarterly: bool = True
) -> UniverseCompany:
    return UniverseCompany(
        cik=cik,
        name=name,
        ticker=ticker,
        sector="Financial Services",
        exchange="NYSE",
        market_cap=Decimal(cap),
        industry="Banks - Regional",
        files_quarterly=quarterly,
    )


def _snapshot() -> UniverseSnapshot:
    return UniverseSnapshot(
        as_of=AS_OF,
        source="fmp_universe_snapshot",
        companies=[
            _company(
                MIZUHO, "Mizuho Financial Group, Inc.", "MFG", "134856875890", quarterly=False
            ),
            _company(PNC, "The PNC Financial Services Group, Inc.", "PNC", "90030360000"),
            _company(TRUIST, "Truist Financial Corporation", "TFC", "59378640800"),
        ],
    )


def test_snapshot_without_the_flag_loads_as_quarterly_filers(tmp_path: Path) -> None:
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps(
            {
                "as_of": "2026-09-26T21:03:37Z",
                "companies": [
                    {
                        "cik": PNC,
                        "name": "PNC",
                        "ticker": "PNC",
                        "sector": "Financial Services",
                        "market_cap": "1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert load_universe_snapshot(path).companies[0].files_quarterly is True


def test_snapshot_json_writes_only_the_exceptions(tmp_path: Path) -> None:
    path = write_universe_snapshot(_snapshot(), tmp_path / "snapshot.json")
    rows = json.loads(path.read_text(encoding="utf-8"))["companies"]
    assert rows[0]["files_quarterly"] is False
    assert "files_quarterly" not in rows[1]
    assert load_universe_snapshot(path) == _snapshot()


def test_ranking_and_peers_skip_foreign_filers_but_lookup_finds_them() -> None:
    ranking = SnapshotRanking(_snapshot())

    table = ranking.rank_companies("regional banks", 10)

    assert [company.ticker for company in table.companies] == ["PNC", "TFC"]
    assert [peer.ticker for peer in ranking.peers(TRUIST)] == ["PNC"]
    assert ranking.lookup_member("MFG").cik == MIZUHO


class _FakeSEC:
    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self._payloads = payloads

    def get_submissions(self, cik: str) -> dict[str, Any]:
        if cik not in self._payloads:
            raise ProviderError("SEC client error", details={"status_code": 404})
        return self._payloads[cik]

    def close(self) -> None:
        pass


def _unflagged() -> UniverseSnapshot:
    snapshot = _snapshot()
    companies = [c.model_copy(update={"files_quarterly": True}) for c in snapshot.companies]
    return snapshot.model_copy(update={"companies": companies})


def test_annotate_filers_changes_only_the_flag() -> None:
    before = _unflagged()
    sec = _FakeSEC(
        {
            MIZUHO: _submissions(("20-F", "2026-06-20")),
            PNC: _submissions(("10-Q", "2026-08-01")),
        }
    )

    after, failed = annotate_filers(before, sec, workers=2)

    assert failed == [TRUIST]
    assert [company.files_quarterly for company in after.companies] == [False, True, True]
    assert after.as_of == before.as_of
    assert [c.model_dump(exclude={"files_quarterly"}) for c in after.companies] == [
        c.model_dump(exclude={"files_quarterly"}) for c in before.companies
    ]


def test_main_annotates_an_existing_snapshot_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "universe_snapshot.json"
    write_universe_snapshot(_unflagged(), path)
    monkeypatch.setenv("SEC_USER_AGENT", "FinancialAnalystAgent (test@example.com)")
    sec = _FakeSEC(
        {
            MIZUHO: _submissions(("20-F", "2026-06-20")),
            PNC: _submissions(("10-Q", "2026-08-01")),
            TRUIST: _submissions(("10-K", "2026-02-20")),
        }
    )
    monkeypatch.setattr(snapshot_builder, "_sec_submissions_source", lambda _settings: sec)

    snapshot_builder.main(["--annotate-filers", "--output", str(path)])

    assert load_universe_snapshot(path) == _snapshot()
    expected = write_universe_snapshot(_snapshot(), tmp_path / "expected.json")
    assert path.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")


def test_packaged_fixture_snapshot_lists_only_quarterly_filers() -> None:
    snapshot = load_universe_snapshot(FIXTURE_UNIVERSE_SNAPSHOT_PATH)
    assert all(company.files_quarterly for company in snapshot.companies)
