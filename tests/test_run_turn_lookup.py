"""Gold: Google latest-quarter net income through run_turn."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from financial_analyst_agent.domain.errors import AmbiguousFactError
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.runtime import DemoCompleter, build_runtime, fixture_runtime
from financial_analyst_agent.turn import Intent, RendererKind, Runtime, run_turn

GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY = (
    "What was Google's net income based on their latest quarterly report?"
)
UNKNOWN_METRIC_QUERY = "What was Google's ROE based on their latest quarterly report?"
UNKNOWN_COSTS_QUERY = "What was Google's costs based on their latest quarterly report?"
GOOGLE_GROSS_PROFIT_QUERY = (
    "What was Google's gross profit based on their latest quarterly report?"
)
GOOGLE_OPERATING_MARGIN_QUERY = (
    "What was Google's operating margin based on their latest quarterly report?"
)
UNRELATED_QUERY = "What is the weather in Atlanta?"
EXXONMOBIL_NET_INCOME_QUERY = (
    "What was ExxonMobil's net income based on their latest quarterly report?"
)
XOM_NET_INCOME_QUERY = "What was XOM's net income based on their latest quarterly report?"
EXXON_NET_INCOME_QUERY = "What was Exxon's net income based on their latest quarterly report?"
APPL_NET_INCOME_QUERY = "What was Appl's net income based on their latest quarterly report?"
SUCCESSOR_TICKERS = {
    "0": {"cik_str": 2115436, "ticker": "XOM", "title": "ExxonMobil Holdings Corp"},
    "1": {"cik_str": 2014337, "ticker": "NPT", "title": "Texxon Holding Ltd"},
    "2": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "3": {"cik_str": 1418121, "ticker": "APLE", "title": "Apple Hospitality REIT, Inc."},
}

# Closed catalog from the PRD: reported facts plus allowed formulas.
ALLOWED_METRICS = (
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_expenses",
    "operating_income",
    "net_income",
    "gross_margin",
    "operating_margin",
    "net_margin",
)

# Fixture-runtime gold literals (recorded Alphabet quarterly fact, not live SEC).
ALPHABET_CIK = "0001652044"
ALPHABET_NAME = "Alphabet Inc."
ALPHABET_TICKER = "GOOG"
NET_INCOME = Decimal("20000000000")
PERIOD_START = date(2026, 4, 1)
PERIOD_END = date(2026, 6, 30)
FORM = "10-Q"
ACCESSION = "0001652044-26-000071"
TAXONOMY = "us-gaap"
CONCEPT = "NetIncomeLoss"
SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/1652044/"
    "000165204426000071/goog-20260630.htm"
)


class _FakeCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        if query != GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return SimpleNamespace(intent=Intent.LOOKUP, company="Google", metric="net_income")


class _FixtureFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        if company != "Google" or metric != "net_income":
            raise AssertionError(f"unexpected get_financials({company!r}, {metric!r})")
        return SimpleNamespace(
            company_name=ALPHABET_NAME,
            ticker=ALPHABET_TICKER,
            cik=ALPHABET_CIK,
            metric="net_income",
            value=NET_INCOME,
            currency="USD",
            start_date=PERIOD_START,
            end_date=PERIOD_END,
            form=FORM,
            accession_number=ACCESSION,
            taxonomy=TAXONOMY,
            concept=CONCEPT,
            source_url=SOURCE_URL,
        )


class _UnknownMetricCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        if query != UNKNOWN_METRIC_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return SimpleNamespace(intent=Intent.LOOKUP, company="Google", metric="roe")


class _FormulaCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        return SimpleNamespace(intent=Intent.LOOKUP, company="Google", metric="operating_margin")


class _ExplodingFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        raise AssertionError("get_financials must not invent a number for an unknown metric")


class _SuccessorFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        resolved = resolve_company(company, SUCCESSOR_TICKERS)
        return SimpleNamespace(
            company_name=resolved.name,
            ticker=resolved.tickers[0],
            cik=resolved.cik,
            metric=metric,
            value=Decimal("14525000000"),
            currency="USD",
            start_date=PERIOD_START,
            end_date=PERIOD_END,
            form=FORM,
            accession_number="0000034088-26-000093",
            taxonomy=TAXONOMY,
            concept=CONCEPT,
            source_url=(
                "https://www.sec.gov/Archives/edgar/data/2115436/"
                "000003408826000093/xom-20260630.htm"
            ),
        )


def test_run_turn_returns_lookup_table_for_google_latest_quarter_net_income() -> None:
    result = run_turn(
        GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY,
        Runtime(completer=_FakeCompleter(), facts=_FixtureFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.banners == []
    assert result.numeral_lock_extras == []

    assert len(result.tool_traces) == 1
    trace = result.tool_traces[0]
    assert trace.tool == "get_financials"
    assert trace.args == {"company": "Google", "metric": "net_income"}
    assert trace.provenance["accession_number"] == ACCESSION
    assert trace.provenance["concept"] == CONCEPT
    assert trace.provenance["source_url"] == SOURCE_URL
    assert trace.provenance["start_date"] == PERIOD_START.isoformat()
    assert trace.provenance["end_date"] == PERIOD_END.isoformat()

    assert len(result.table_rows) == 1
    row = result.table_rows[0]
    assert row.company_name == ALPHABET_NAME
    assert row.ticker == ALPHABET_TICKER
    assert row.cik == ALPHABET_CIK
    assert row.metric == "net_income"
    assert row.value == NET_INCOME
    assert row.start_date == PERIOD_START
    assert row.end_date == PERIOD_END
    assert row.form == FORM
    assert row.accession_number == ACCESSION
    assert row.taxonomy == TAXONOMY
    assert row.concept == CONCEPT
    assert row.source_url == SOURCE_URL


@pytest.mark.gold
def test_run_turn_resolves_google_and_selects_standalone_quarter() -> None:
    result = run_turn(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, fixture_runtime())

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.company_name == ALPHABET_NAME
    assert row.cik == ALPHABET_CIK
    assert row.ticker == ALPHABET_TICKER
    assert row.value == NET_INCOME
    assert row.start_date == PERIOD_START
    assert row.end_date == PERIOD_END
    assert row.accession_number == ACCESSION
    assert row.concept == CONCEPT
    assert row.source_url == SOURCE_URL


def test_build_runtime_fixture_mode_uses_recorded_facts() -> None:
    result = run_turn(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, build_runtime())
    assert result.intent is Intent.LOOKUP
    assert result.table_rows[0].company_name == ALPHABET_NAME
    assert result.table_rows[0].value == NET_INCOME
    assert result.table_rows[0].accession_number == ACCESSION


def test_run_turn_refuses_unknown_metric_with_allowed_list() -> None:
    result = run_turn(
        UNKNOWN_METRIC_QUERY,
        Runtime(completer=_UnknownMetricCompleter(), facts=_ExplodingFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.numeral_lock_extras == []
    assert result.message is not None
    assert "roe" in result.message.casefold()
    for metric in ALLOWED_METRICS:
        assert metric in result.message


def test_fixture_runtime_refuses_unknown_costs_without_inventing_net_income() -> None:
    result = run_turn(UNKNOWN_COSTS_QUERY, fixture_runtime())
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.message is not None
    assert "costs" in result.message.casefold()
    for metric in ALLOWED_METRICS:
        assert metric in result.message


def test_fixture_runtime_refuses_lookup_of_formula_metric() -> None:
    result = run_turn(GOOGLE_OPERATING_MARGIN_QUERY, fixture_runtime())
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.message is not None
    assert "operating_margin" in result.message
    for metric in ALLOWED_METRICS:
        assert metric in result.message


def test_fixture_runtime_does_not_invent_net_income_for_unrelated_query() -> None:
    result = run_turn(UNRELATED_QUERY, fixture_runtime())
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert all(row.value != NET_INCOME for row in result.table_rows)


def test_fixture_runtime_refuses_when_recorded_fact_missing_for_gross_profit() -> None:
    result = run_turn(GOOGLE_GROSS_PROFIT_QUERY, fixture_runtime())
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.message is not None


def test_run_turn_refuses_formula_metric_from_completer_without_calling_facts() -> None:
    result = run_turn(
        GOOGLE_OPERATING_MARGIN_QUERY,
        Runtime(
            completer=_FormulaCompleter(),
            facts=_ExplodingFacts(),
        ),
    )
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.message is not None
    assert "operating_margin" in result.message


def _assert_successor_lookup(query: str) -> None:
    result = run_turn(
        query,
        Runtime(completer=DemoCompleter(), facts=_SuccessorFacts()),
    )
    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    row = result.table_rows[0]
    assert row.cik == "0002115436"
    assert row.ticker == "XOM"
    assert row.company_name == "ExxonMobil Holdings Corp"
    assert row.value == Decimal("14525000000")
    assert result.tool_traces[0].args["metric"] == "net_income"


def test_run_turn_lookup_resolves_exxonmobil_successor_name() -> None:
    _assert_successor_lookup(EXXONMOBIL_NET_INCOME_QUERY)


def test_run_turn_lookup_resolves_xom_ticker() -> None:
    _assert_successor_lookup(XOM_NET_INCOME_QUERY)


def test_run_turn_lookup_resolves_exxon_prefix() -> None:
    _assert_successor_lookup(EXXON_NET_INCOME_QUERY)


def test_run_turn_refuses_conflicting_catalog_concepts() -> None:
    class _AmbiguousFacts:
        def get_financials(self, company: str, metric: str) -> SimpleNamespace:
            raise AmbiguousFactError(
                "Supported concepts produced conflicting quarterly values",
                details={"metric": metric, "concepts": ["NetIncomeLoss", "ProfitLoss"]},
            )

    result = run_turn(
        XOM_NET_INCOME_QUERY,
        Runtime(completer=DemoCompleter(), facts=_AmbiguousFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.message is not None
    assert "conflicting" in result.message.casefold()


def test_run_turn_refuses_ambiguous_company_prefix() -> None:
    result = run_turn(
        APPL_NET_INCOME_QUERY,
        Runtime(completer=DemoCompleter(), facts=_SuccessorFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.message is not None
    assert "appl" in result.message.casefold() or "multiple" in result.message.casefold()
