"""Labeled gold suite: Thursday demo prompts through fixture_runtime."""

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.news import FIXTURE_NEWS_QUERY
from financial_analyst_agent.runtime import fixture_runtime
from financial_analyst_agent.turn import Intent, RendererKind, run_turn

pytestmark = pytest.mark.gold

MICROSOFT_PRETAX_QUERY = "Microsoft pre-tax income"
TSLA_GM_REVENUE_QUERY = "TSLA vs GM revenue"
TECH_RD_QUERY = "Top 10 tech companies R&D spend"
SNAPSHOT_AS_OF = "2026-08-17T16:00:00+00:00"
TECHNOLOGY_TOP_10 = (
    ("Apple Inc.", "AAPL", "0000320193", Decimal("3500000000000")),
    ("Microsoft Corporation", "MSFT", "0000789019", Decimal("3100000000000")),
    ("Alphabet Inc.", "GOOG", "0001652044", Decimal("2200000000000")),
    ("NVIDIA Corporation", "NVDA", "0001045810", Decimal("1800000000000")),
    ("Broadcom Inc.", "AVGO", "0001730168", Decimal("900000000000")),
    ("Oracle Corporation", "ORCL", "0001341439", Decimal("650000000000")),
    ("Advanced Micro Devices, Inc.", "AMD", "0000002488", Decimal("600000000000")),
    ("Cisco Systems, Inc.", "CSCO", "0000858877", Decimal("450000000000")),
    ("Palantir Technologies Inc.", "PLTR", "0001321655", Decimal("400000000000")),
    ("Applied Materials, Inc.", "AMAT", "0000006951", Decimal("350000000000")),
)

MICROSOFT_CIK = "0000789019"
MICROSOFT_TICKER = "MSFT"
MICROSOFT_PRETAX = Decimal("32014000000")
MICROSOFT_ACCESSION = "0001193125-26-191507"
MICROSOFT_PRETAX_CONCEPT = "PretaxIncomeLoss"
MICROSOFT_SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/msft-20260331.htm"
)
PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 3, 31)

TESLA_CIK = "0001318605"
TESLA_REVENUE = Decimal("19335000000")
GM_CIK = "0001467858"
GM_REVENUE = Decimal("44019000000")

APPLE_RD = Decimal("8042000000")
MICROSOFT_RD = Decimal("8197000000")
ALPHABET_RD = Decimal("13838000000")
NVIDIA_RD = Decimal("3900000000")
BROADCOM_RD = Decimal("1500000000")
ORACLE_RD = Decimal("2300000000")
AMD_RD = Decimal("1600000000")
CISCO_RD = Decimal("2000000000")
PALANTIR_RD = Decimal("300000000")
AMAT_RD = Decimal("900000000")
TECH_RD_VALUES = (
    APPLE_RD,
    MICROSOFT_RD,
    ALPHABET_RD,
    NVIDIA_RD,
    BROADCOM_RD,
    ORACLE_RD,
    AMD_RD,
    CISCO_RD,
    PALANTIR_RD,
    AMAT_RD,
)


def test_gold_microsoft_pretax_income_through_kill_switch_runtime() -> None:
    result = run_turn(MICROSOFT_PRETAX_QUERY, fixture_runtime())

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.cik == MICROSOFT_CIK
    assert row.ticker == MICROSOFT_TICKER
    assert row.metric == "pretax_income"
    assert row.value == MICROSOFT_PRETAX
    assert row.accession_number == MICROSOFT_ACCESSION
    assert row.form == "10-Q"
    assert row.concept == MICROSOFT_PRETAX_CONCEPT
    assert row.start_date == PERIOD_START
    assert row.end_date == PERIOD_END
    assert row.source_url == MICROSOFT_SOURCE_URL


def test_gold_tsla_vs_gm_revenue_through_kill_switch_runtime() -> None:
    result = run_turn(TSLA_GM_REVENUE_QUERY, fixture_runtime())

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.TABLE
    tesla, gm = result.table_rows
    assert tesla.cik == TESLA_CIK
    assert tesla.ticker == "TSLA"
    assert tesla.metric == "revenue"
    assert tesla.value == TESLA_REVENUE
    assert tesla.start_date == PERIOD_START
    assert tesla.end_date == PERIOD_END
    assert gm.cik == GM_CIK
    assert gm.ticker == "GM"
    assert gm.value == GM_REVENUE
    assert gm.start_date == PERIOD_START
    assert gm.end_date == PERIOD_END


def test_gold_top_tech_rd_spend_through_kill_switch_runtime() -> None:
    result = run_turn(TECH_RD_QUERY, fixture_runtime())

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
    assert [row.cik for row in result.table_rows].count("0001652044") == 1
    assert "GOOGL" not in [row.ticker for row in result.table_rows]
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


def test_gold_hormuz_exxon_news_through_kill_switch_runtime() -> None:
    result = run_turn(FIXTURE_NEWS_QUERY, fixture_runtime())

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
