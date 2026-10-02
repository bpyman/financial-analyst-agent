"""Labeled gold suite: Thursday demo prompts through the recorded runtime."""

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind
from financial_analyst_agent.news import FIXTURE_NEWS_QUERY
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.turn import run_turn

pytestmark = pytest.mark.gold

MICROSOFT_PRETAX_QUERY = "Microsoft pre-tax income"
TSLA_GM_REVENUE_QUERY = "TSLA vs GM revenue"
TECH_RD_QUERY = "Top 10 tech companies R&D spend"
SNAPSHOT_AS_OF = "2026-09-27T22:43:45.015184+00:00"
TECHNOLOGY_TOP_10 = (
    # The live snapshot's top ten: Alphabet is Communication Services there.
    ("NVIDIA Corporation", "NVDA", "0001045810", Decimal("5451420470000")),
    ("Apple Inc.", "AAPL", "0000320193", Decimal("5009416510920")),
    ("Microsoft Corporation", "MSFT", "0000789019", Decimal("3832846143500")),
    ("Broadcom Inc.", "AVGO", "0001730168", Decimal("1678521799800")),
    ("Micron Technology, Inc.", "MU", "0000723125", Decimal("1222316209200")),
    ("Advanced Micro Devices, Inc.", "AMD", "0000002488", Decimal("1028305278000")),
    ("Intel Corp.", "INTC", "0000050863", Decimal("620411968881")),
    ("Palantir Technologies Inc.", "PLTR", "0001321655", Decimal("435495596900")),
    ("Cisco Systems, Inc.", "CSCO", "0000858877", Decimal("420551078756")),
    ("Oracle Corporation", "ORCL", "0001341439", Decimal("394854827600")),
)

MICROSOFT_CIK = "0000789019"
MICROSOFT_TICKER = "MSFT"
MICROSOFT_PRETAX = Decimal("44047000000")
MICROSOFT_ACCESSION = "0001193125-26-323660"
MICROSOFT_PRETAX_CONCEPT = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)
MICROSOFT_SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm"
)
PERIOD_START = date(2026, 4, 1)
PERIOD_END = date(2026, 6, 30)
LATEST_QUARTER_START = date(2026, 4, 1)
LATEST_QUARTER_END = date(2026, 6, 30)

TESLA_CIK = "0001318605"
TESLA_REVENUE = Decimal("28236000000")
GM_CIK = "0001467858"
# GM's total net sales and revenue (``Revenues``), with GM Financial.
GM_REVENUE = Decimal("48026000000")

APPLE_RD = Decimal("11729000000")
MICROSOFT_RD = Decimal("9997000000")
MICRON_RD = Decimal("1316000000")
INTEL_RD = Decimal("3368000000")
NVIDIA_RD = Decimal("7054000000")
BROADCOM_RD = Decimal("2895000000")
ORACLE_RD = Decimal("2401000000")
AMD_RD = Decimal("2528000000")
CISCO_RD = Decimal("2431000000")
PALANTIR_RD = Decimal("192513000")
TECH_RD_VALUES = (
    NVIDIA_RD,
    APPLE_RD,
    MICROSOFT_RD,
    BROADCOM_RD,
    MICRON_RD,
    AMD_RD,
    INTEL_RD,
    PALANTIR_RD,
    CISCO_RD,
    ORACLE_RD,
)


def test_gold_microsoft_pretax_income_through_recorded_runtime() -> None:
    result = run_turn(MICROSOFT_PRETAX_QUERY, recorded_runtime())

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.cik == MICROSOFT_CIK
    assert row.ticker == MICROSOFT_TICKER
    assert row.metric == "pretax_income"
    assert row.value == MICROSOFT_PRETAX
    assert row.accession_number == MICROSOFT_ACCESSION
    # The latest quarter is fiscal Q4: the 10-K year minus the 10-Q nine months.
    assert row.form == "10-K"
    assert row.derivation is not None
    assert [part.value for part in row.derived_from] == [
        Decimal("165934000000"),
        Decimal("121887000000"),
    ]
    assert row.concept == MICROSOFT_PRETAX_CONCEPT
    assert row.start_date == PERIOD_START
    assert row.end_date == PERIOD_END
    assert row.source_url == MICROSOFT_SOURCE_URL


def test_gold_tsla_vs_gm_revenue_through_recorded_runtime() -> None:
    result = run_turn(TSLA_GM_REVENUE_QUERY, recorded_runtime())

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.TABLE
    tesla, gm = result.table_rows
    assert tesla.cik == TESLA_CIK
    assert tesla.ticker == "TSLA"
    assert tesla.metric == "revenue"
    assert tesla.value == TESLA_REVENUE
    assert tesla.start_date == LATEST_QUARTER_START
    assert tesla.end_date == LATEST_QUARTER_END
    assert gm.cik == GM_CIK
    assert gm.ticker == "GM"
    assert gm.value == GM_REVENUE
    assert gm.start_date == LATEST_QUARTER_START
    assert gm.end_date == LATEST_QUARTER_END


def test_gold_top_tech_rd_spend_through_recorded_runtime() -> None:
    result = run_turn(TECH_RD_QUERY, recorded_runtime())

    assert result.intent is Intent.RANK_AND_LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.banners == [f"Universe snapshot as of {SNAPSHOT_AS_OF}"]
    rank_traces = [t for t in result.tool_traces if t.tool == "rank_companies"]
    assert len(rank_traces) == 1
    assert rank_traces[0].args["limit"] == 10
    assert len(result.table_rows) == len(TECHNOLOGY_TOP_10) == 10
    assert [row.ticker for row in result.table_rows] == [
        ticker for _name, ticker, _cik, _cap in TECHNOLOGY_TOP_10
    ]
    caps = [cap for _name, _ticker, _cik, cap in TECHNOLOGY_TOP_10]
    assert caps == sorted(caps, reverse=True)
    lookup_ciks = [
        trace.args["company"] for trace in result.tool_traces if trace.tool == "get_financials"
    ]
    assert lookup_ciks == [cik for _name, _ticker, cik, _cap in TECHNOLOGY_TOP_10]
    for row, (_name, ticker, cik, _cap), value in zip(
        result.table_rows, TECHNOLOGY_TOP_10, TECH_RD_VALUES, strict=True
    ):
        assert row.ticker == ticker
        assert row.cik == cik
        assert row.metric == "research_and_development"
        assert row.value == value
        assert row.reason is None


def test_gold_hormuz_exxon_news_through_recorded_runtime() -> None:
    result = run_turn(FIXTURE_NEWS_QUERY, recorded_runtime())

    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.renderer is RendererKind.ESSAY
    assert result.essay is not None
    assert "Hormuz" in result.essay
    assert "$1.2B" in result.essay
    assert result.numeral_lock_extras == []
    assert result.citations
    assert all(hit.title and hit.url for hit in result.citations)
    assert result.tool_traces[0].tool == "search_news"
    assert result.tool_traces[0].args["query"] == FIXTURE_NEWS_QUERY
