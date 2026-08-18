"""Labeled gold suite: the three live prompts plus one refuse through fixture_runtime."""

from decimal import Decimal

import pytest

from financial_analyst_agent.runtime import fixture_runtime
from financial_analyst_agent.turn import Intent, RendererKind, run_turn
from test_run_turn_compare import (
    ALPHABET_OPERATING_MARGIN,
    MICROSOFT_CIK,
    MICROSOFT_OPERATING_MARGIN,
    MSFT_GOOG_OPERATING_MARGINS_QUERY,
)
from test_run_turn_lookup import (
    ACCESSION,
    ALPHABET_CIK,
    ALPHABET_TICKER,
    CONCEPT,
    FORM,
    GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY,
    NET_INCOME,
    PERIOD_END,
    PERIOD_START,
    SOURCE_URL,
)
from test_run_turn_rank import HEALTHCARE_TOP_10, SNAPSHOT_AS_OF, UNKNOWN_INDUSTRY_QUERY
from test_run_turn_rank_and_lookup import HEALTHCARE_INCOME_QUERY, LLY_NET_INCOME, UNH_NET_INCOME

pytestmark = pytest.mark.gold


def test_gold_google_net_income_through_kill_switch_runtime() -> None:
    result = run_turn(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, fixture_runtime())

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.cik == ALPHABET_CIK
    assert row.ticker == ALPHABET_TICKER
    assert row.metric == "net_income"
    assert row.value == NET_INCOME
    assert row.accession_number == ACCESSION
    assert row.form == FORM
    assert row.concept == CONCEPT
    assert row.start_date == PERIOD_START
    assert row.end_date == PERIOD_END
    assert row.source_url == SOURCE_URL


def test_gold_healthcare_top_10_and_incomes_through_kill_switch_runtime() -> None:
    result = run_turn(HEALTHCARE_INCOME_QUERY, fixture_runtime())

    assert result.intent is Intent.RANK_AND_LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.banners == [f"Universe snapshot as of {SNAPSHOT_AS_OF}"]
    assert [row.ticker for row in result.table_rows] == [
        ticker for _name, ticker, _cik, _cap in HEALTHCARE_TOP_10
    ]
    assert result.table_rows[0].value == LLY_NET_INCOME
    assert result.table_rows[1].value == UNH_NET_INCOME
    assert result.table_rows[-1].ticker == "PFE"
    assert result.table_rows[-1].value is None
    assert result.table_rows[-1].reason == "missing_fact"
    lookup_ciks = [
        trace.args["company"]
        for trace in result.tool_traces
        if trace.tool == "get_financials"
    ]
    assert lookup_ciks == [cik for _name, _ticker, cik, _cap in HEALTHCARE_TOP_10]


def test_gold_microsoft_vs_google_operating_margins_through_kill_switch_runtime() -> None:
    result = run_turn(MSFT_GOOG_OPERATING_MARGINS_QUERY, fixture_runtime())

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.TABLE
    microsoft, alphabet = result.table_rows
    assert microsoft.cik == MICROSOFT_CIK
    assert alphabet.cik == ALPHABET_CIK
    assert microsoft.value == MICROSOFT_OPERATING_MARGIN
    assert alphabet.value == ALPHABET_OPERATING_MARGIN
    assert microsoft.start_date == PERIOD_START
    assert microsoft.end_date == PERIOD_END
    assert alphabet.start_date == PERIOD_START
    assert alphabet.end_date == PERIOD_END
    assert microsoft.value == Decimal("0.5")
    assert alphabet.value == Decimal("0.35")


def test_gold_unknown_industry_refuses_with_allowed_names() -> None:
    result = run_turn(UNKNOWN_INDUSTRY_QUERY, fixture_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.message is not None
    assert "ai" in result.message.casefold()
    for industry in ("finance", "healthcare", "technology"):
        assert industry in result.message.casefold()
