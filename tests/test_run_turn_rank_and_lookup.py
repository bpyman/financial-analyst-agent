"""Gold: top 10 healthcare and net income for each through run_turn."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from financial_analyst_agent.domain.errors import (
    AmbiguousFactError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.turn import Intent, RendererKind, Runtime, run_turn
from test_run_turn_rank import (
    FIXTURE_SNAPSHOT_PATH,
    HEALTHCARE_TOP_10,
    SNAPSHOT_AS_OF,
    _gold_rank_runtime,
)

HEALTHCARE_INCOME_QUERY = "What are the top 10 healthcare companies and the net income for each?"
HEALTHCARE_NET_MARGINS_QUERY = (
    "What are the top 10 healthcare companies and the net margins of each?"
)

# Fixture-runtime gold literals (recorded 10-Q facts, not live SEC).
PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 3, 31)
FORM = "10-Q"
TAXONOMY = "us-gaap"
CONCEPT = "NetIncomeLoss"

LLY_NET_INCOME = Decimal("7396000000")
LLY_REVENUE = Decimal("73960000000")
LLY_ACCESSION = "0000059478-26-000045"
LLY_SOURCE_URL = "https://www.sec.gov/Archives/edgar/data/59478/000005947826000045/lly-20260331.htm"

UNH_NET_INCOME = Decimal("6481000000")
UNH_REVENUE = Decimal("64810000000")
UNH_ACCESSION = "0000731766-26-000127"
UNH_SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/731766/000073176626000127/unh-20260331.htm"
)
UNH_PERIOD_START = date(2025, 10, 1)
UNH_PERIOD_END = date(2025, 12, 31)
REVENUE_CONCEPT = "RevenueFromContractWithCustomerExcludingAssessedTax"


@pytest.mark.gold
def test_run_turn_returns_rank_and_lookup_table_for_healthcare_incomes() -> None:
    result = run_turn(HEALTHCARE_INCOME_QUERY, _gold_rank_runtime())

    assert result.intent is Intent.RANK_AND_LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.banners == [f"Universe snapshot as of {SNAPSHOT_AS_OF}"]
    assert result.numeral_lock_extras == []
    assert result.message is None

    assert result.tool_traces[0].tool == "rank_companies"
    assert result.tool_traces[0].args == {"industry": "healthcare", "limit": 10}
    assert result.tool_traces[0].provenance["snapshot_as_of"] == SNAPSHOT_AS_OF
    lookup_traces = result.tool_traces[1:]
    assert [trace.tool for trace in lookup_traces] == ["get_financials"] * 10
    assert [trace.args["company"] for trace in lookup_traces] == [
        cik for _name, _ticker, cik, _cap in HEALTHCARE_TOP_10
    ]
    assert {trace.args["metric"] for trace in lookup_traces} == {"net_income"}

    assert len(result.table_rows) == 10
    for index, (name, ticker, cik, _market_cap) in enumerate(HEALTHCARE_TOP_10, start=1):
        row = result.table_rows[index - 1]
        assert row.rank == index
        assert row.company_name == name
        assert row.ticker == ticker
        assert row.cik == cik
        assert row.metric == "net_income"

    lilly, unitedhealth, *middle, pfizer = result.table_rows
    assert lilly.value == LLY_NET_INCOME
    assert lilly.accession_number == LLY_ACCESSION
    assert lilly.concept == CONCEPT
    assert lilly.source_url == LLY_SOURCE_URL
    assert lilly.start_date == PERIOD_START
    assert lilly.end_date == PERIOD_END
    assert lilly.form == FORM
    assert lilly.taxonomy == TAXONOMY
    assert lilly.reason is None

    assert unitedhealth.value == UNH_NET_INCOME
    assert unitedhealth.accession_number == UNH_ACCESSION
    assert unitedhealth.concept == CONCEPT
    assert unitedhealth.source_url == UNH_SOURCE_URL
    assert unitedhealth.reason is None

    assert pfizer.ticker == "PFE"
    assert pfizer.value is None
    assert pfizer.reason == "missing_fact"
    assert pfizer.accession_number is None
    for row in middle:
        if row.ticker not in {"LLY", "UNH"}:
            assert row.value is None
            assert row.reason == "missing_fact"


def test_run_turn_rank_and_lookup_ignores_model_typed_constituents() -> None:
    class _DecoyCompleter:
        def complete(self, query: str) -> SimpleNamespace:
            return SimpleNamespace(
                intent=Intent.RANK_AND_LOOKUP,
                industry="healthcare",
                limit=10,
                metric="net_income",
                companies=["AAPL", "MSFT", "GOOG"],
            )

    result = run_turn(
        HEALTHCARE_INCOME_QUERY,
        Runtime(
            completer=_DecoyCompleter(),
            facts=_CikOnlyFacts(),
            ranking=SnapshotRanking.from_path(FIXTURE_SNAPSHOT_PATH),
        ),
    )

    tickers = [row.ticker for row in result.table_rows]
    assert result.intent is Intent.RANK_AND_LOOKUP
    assert tickers == [ticker for _name, ticker, _cik, _cap in HEALTHCARE_TOP_10]
    assert "AAPL" not in tickers
    lookup_ciks = [
        trace.args["company"] for trace in result.tool_traces if trace.tool == "get_financials"
    ]
    assert lookup_ciks == [cik for _name, _ticker, cik, _cap in HEALTHCARE_TOP_10]


def test_run_turn_rank_and_lookup_keeps_good_rows_when_issuers_have_no_10_q() -> None:
    class _Missing10QFacts(_CikOnlyFacts):
        def get_financials(self, company: str, metric: str) -> SimpleNamespace:
            if company == "0000059478":
                return super().get_financials(company, metric)
            raise UnsupportedQuarterlyFactError("No 10-Q or 10-Q/A filings found")

    result = run_turn(
        HEALTHCARE_INCOME_QUERY,
        Runtime(
            completer=_gold_rank_runtime().completer,
            facts=_Missing10QFacts(),
            ranking=SnapshotRanking.from_path(FIXTURE_SNAPSHOT_PATH),
        ),
    )

    assert len(result.table_rows) == 10
    assert result.table_rows[0].value == LLY_NET_INCOME
    assert result.table_rows[0].reason is None
    assert all(row.reason == "missing_fact" for row in result.table_rows[1:])


class _CikOnlyFacts:
    """Resolves recorded facts by ranking CIK only — a typed ticker list would miss."""

    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        if company == "0000059478" and metric == "net_income":
            return _fact(
                "Eli Lilly and Company",
                "LLY",
                "0000059478",
                LLY_NET_INCOME,
                LLY_ACCESSION,
                LLY_SOURCE_URL,
            )
        if company == "0000731766" and metric == "net_income":
            return _fact(
                "UnitedHealth Group Incorporated",
                "UNH",
                "0000731766",
                UNH_NET_INCOME,
                UNH_ACCESSION,
                UNH_SOURCE_URL,
            )
        raise UnsupportedQuarterlyFactError(
            "No directly reported standalone-quarter fact exists for metric"
        )


def _fact(
    name: str,
    ticker: str,
    cik: str,
    value: Decimal,
    accession: str,
    source_url: str,
    *,
    metric: str = "net_income",
    concept: str = CONCEPT,
    start_date: date = PERIOD_START,
    end_date: date = PERIOD_END,
) -> SimpleNamespace:
    return SimpleNamespace(
        company_name=name,
        ticker=ticker,
        cik=cik,
        metric=metric,
        value=value,
        currency="USD",
        start_date=start_date,
        end_date=end_date,
        form=FORM,
        accession_number=accession,
        taxonomy=TAXONOMY,
        concept=concept,
        source_url=source_url,
        source="sec_xbrl",
    )


def test_run_turn_rank_and_lookup_preserves_ambiguous_fact_reason() -> None:
    class _AmbiguousLillyFacts(_CikOnlyFacts):
        def get_financials(self, company: str, metric: str) -> SimpleNamespace:
            if company == "0000059478":
                raise AmbiguousFactError("Supported concepts produced conflicting values")
            return super().get_financials(company, metric)

    result = run_turn(
        HEALTHCARE_INCOME_QUERY,
        Runtime(
            completer=_gold_rank_runtime().completer,
            facts=_AmbiguousLillyFacts(),
            ranking=SnapshotRanking.from_path(FIXTURE_SNAPSHOT_PATH),
        ),
    )

    lilly, unitedhealth, *remaining = result.table_rows
    assert lilly.reason == "ambiguous_concept"
    assert unitedhealth.value == UNH_NET_INCOME
    assert all(row.reason == "missing_fact" for row in remaining)


def test_run_turn_rank_and_lookup_computes_net_margin_per_ranked_issuer() -> None:
    result = run_turn(
        HEALTHCARE_NET_MARGINS_QUERY,
        Runtime(
            completer=_RankAndLookupNetMarginCompleter(),
            facts=_CikMarginFacts(),
            ranking=SnapshotRanking.from_path(FIXTURE_SNAPSHOT_PATH),
        ),
    )

    assert result.intent is Intent.RANK_AND_LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.message is None
    assert result.tool_traces[0].tool == "rank_companies"
    lookup_traces = result.tool_traces[1:]
    assert [trace.tool for trace in lookup_traces] == ["compare_metrics"] * 10
    assert [trace.args for trace in lookup_traces] == [
        {"issuers": [cik], "metric": "net_margin"}
        for _name, _ticker, cik, _cap in HEALTHCARE_TOP_10
    ]

    assert len(result.table_rows) == 10
    lilly, unitedhealth, *remaining = result.table_rows
    assert lilly.rank == 1
    assert lilly.ticker == "LLY"
    assert lilly.cik == "0000059478"
    assert lilly.metric == "net_margin"
    assert lilly.value == LLY_NET_INCOME / LLY_REVENUE
    assert lilly.start_date == PERIOD_START
    assert lilly.end_date == PERIOD_END
    assert lilly.reason is None
    components = {component.metric: component for component in lilly.components}
    assert components["net_income"].value == LLY_NET_INCOME
    assert components["revenue"].value == LLY_REVENUE
    assert components["net_income"].form == FORM
    assert components["net_income"].taxonomy == TAXONOMY
    assert components["net_income"].source == "sec_xbrl"

    assert unitedhealth.ticker == "UNH"
    assert unitedhealth.value == UNH_NET_INCOME / UNH_REVENUE
    assert unitedhealth.start_date == UNH_PERIOD_START
    assert unitedhealth.end_date == UNH_PERIOD_END
    assert unitedhealth.reason is None

    lilly_trace = lookup_traces[0]
    provenance = {item["metric"]: item for item in lilly_trace.provenance["components"]}
    assert provenance["net_income"]["value"] == str(LLY_NET_INCOME)
    assert provenance["revenue"]["value"] == str(LLY_REVENUE)
    assert provenance["net_income"]["form"] == FORM
    assert provenance["net_income"]["taxonomy"] == TAXONOMY
    assert provenance["net_income"]["source"] == "sec_xbrl"
    assert provenance["net_income"]["cik"] == "0000059478"

    for row in remaining:
        assert row.metric == "net_margin"
        assert row.value is None
        assert row.reason == "missing_fact"
        assert row.ticker in {ticker for _name, ticker, _cik, _cap in HEALTHCARE_TOP_10}


class _RankAndLookupNetMarginCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        if query != HEALTHCARE_NET_MARGINS_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return SimpleNamespace(
            intent=Intent.RANK_AND_LOOKUP,
            industry="healthcare",
            limit=10,
            metric="net_margin",
        )


class _CikMarginFacts:
    """Net income and revenue per ranking CIK; issuers keep different fiscal calendars."""

    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        if company == "0000059478":
            if metric == "net_income":
                return _fact(
                    "Eli Lilly and Company",
                    "LLY",
                    "0000059478",
                    LLY_NET_INCOME,
                    LLY_ACCESSION,
                    LLY_SOURCE_URL,
                )
            if metric == "revenue":
                return _fact(
                    "Eli Lilly and Company",
                    "LLY",
                    "0000059478",
                    LLY_REVENUE,
                    LLY_ACCESSION,
                    LLY_SOURCE_URL,
                    metric="revenue",
                    concept=REVENUE_CONCEPT,
                )
        if company == "0000731766":
            if metric == "net_income":
                return _fact(
                    "UnitedHealth Group Incorporated",
                    "UNH",
                    "0000731766",
                    UNH_NET_INCOME,
                    UNH_ACCESSION,
                    UNH_SOURCE_URL,
                    start_date=UNH_PERIOD_START,
                    end_date=UNH_PERIOD_END,
                )
            if metric == "revenue":
                return _fact(
                    "UnitedHealth Group Incorporated",
                    "UNH",
                    "0000731766",
                    UNH_REVENUE,
                    UNH_ACCESSION,
                    UNH_SOURCE_URL,
                    metric="revenue",
                    concept=REVENUE_CONCEPT,
                    start_date=UNH_PERIOD_START,
                    end_date=UNH_PERIOD_END,
                )
        raise UnsupportedQuarterlyFactError(
            "No directly reported standalone-quarter fact exists for metric"
        )
