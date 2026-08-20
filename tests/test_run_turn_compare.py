"""Gold: Microsoft vs Google operating margins through run_turn."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from financial_analyst_agent.domain.errors import AmbiguousFactError, UnsupportedQuarterlyFactError
from financial_analyst_agent.facts import RecordedSECDataSource
from financial_analyst_agent.runtime import fixture_runtime
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.turn import Intent, RendererKind, Runtime, run_turn
from test_run_turn_lookup import ALLOWED_METRICS

MSFT_GOOG_OPERATING_MARGINS_QUERY = (
    "compare Microsoft and Google operating margins"
)
UNKNOWN_RATIO_QUERY = "compare Microsoft and Google ROE"

# Fixture-runtime gold literals (recorded facts, not live SEC).
ALPHABET_CIK = "0001652044"
ALPHABET_NAME = "Alphabet Inc."
ALPHABET_TICKER = "GOOG"
MICROSOFT_CIK = "0000789019"
MICROSOFT_NAME = "Microsoft Corporation"
MICROSOFT_TICKER = "MSFT"
PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 3, 31)
FORM = "10-Q"
TAXONOMY = "us-gaap"

# operating_margin = operating_income / revenue (Decimal, not LLM arithmetic)
MICROSOFT_OPERATING_INCOME = Decimal("38398000000")
MICROSOFT_REVENUE = Decimal("82886000000")
MICROSOFT_OPERATING_MARGIN = MICROSOFT_OPERATING_INCOME / MICROSOFT_REVENUE
MICROSOFT_ACCESSION = "0001193125-26-191507"
MICROSOFT_OPERATING_INCOME_CONCEPT = "OperatingIncomeLoss"
MICROSOFT_REVENUE_CONCEPT = "RevenueFromContractWithCustomerExcludingAssessedTax"
MICROSOFT_SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/789019/"
    "000119312526191507/msft-20260331.htm"
)

ALPHABET_OPERATING_INCOME = Decimal("39696000000")
ALPHABET_REVENUE = Decimal("109896000000")
ALPHABET_OPERATING_MARGIN = ALPHABET_OPERATING_INCOME / ALPHABET_REVENUE
ALPHABET_ACCESSION = "0001652044-26-000048"
ALPHABET_OPERATING_INCOME_CONCEPT = "OperatingIncomeLoss"
ALPHABET_REVENUE_CONCEPT = "RevenueFromContractWithCustomerExcludingAssessedTax"
ALPHABET_SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/1652044/"
    "000165204426000048/goog-20260331.htm"
)


def test_run_turn_returns_compare_table_for_microsoft_and_google_operating_margins() -> None:
    result = run_turn(MSFT_GOOG_OPERATING_MARGINS_QUERY, fixture_runtime())

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.TABLE
    assert result.banners == []
    assert result.numeral_lock_extras == []
    assert result.message is None

    assert len(result.tool_traces) == 1
    trace = result.tool_traces[0]
    assert trace.tool == "compare_metrics"
    assert trace.args["issuers"] == ["Microsoft", "Google"]
    assert trace.args["metric"] == "operating_margin"

    assert len(result.table_rows) == 2
    microsoft, alphabet = result.table_rows
    assert microsoft.company_name == MICROSOFT_NAME
    assert microsoft.ticker == MICROSOFT_TICKER
    assert microsoft.cik == MICROSOFT_CIK
    assert microsoft.metric == "operating_margin"
    assert microsoft.value == MICROSOFT_OPERATING_MARGIN
    assert microsoft.start_date == PERIOD_START
    assert microsoft.end_date == PERIOD_END
    assert microsoft.reason is None
    _assert_operating_margin_components(
        microsoft,
        operating_income=MICROSOFT_OPERATING_INCOME,
        revenue=MICROSOFT_REVENUE,
        accession=MICROSOFT_ACCESSION,
        operating_income_concept=MICROSOFT_OPERATING_INCOME_CONCEPT,
        revenue_concept=MICROSOFT_REVENUE_CONCEPT,
        source_url=MICROSOFT_SOURCE_URL,
    )

    assert alphabet.company_name == ALPHABET_NAME
    assert alphabet.ticker == ALPHABET_TICKER
    assert alphabet.cik == ALPHABET_CIK
    assert alphabet.metric == "operating_margin"
    assert alphabet.value == ALPHABET_OPERATING_MARGIN
    assert alphabet.start_date == PERIOD_START
    assert alphabet.end_date == PERIOD_END
    assert alphabet.reason is None
    _assert_operating_margin_components(
        alphabet,
        operating_income=ALPHABET_OPERATING_INCOME,
        revenue=ALPHABET_REVENUE,
        accession=ALPHABET_ACCESSION,
        operating_income_concept=ALPHABET_OPERATING_INCOME_CONCEPT,
        revenue_concept=ALPHABET_REVENUE_CONCEPT,
        source_url=ALPHABET_SOURCE_URL,
    )


def _assert_operating_margin_components(
    row: object,
    *,
    operating_income: Decimal,
    revenue: Decimal,
    accession: str,
    operating_income_concept: str,
    revenue_concept: str,
    source_url: str,
) -> None:
    components = {component.metric: component for component in row.components}
    assert set(components) == {"operating_income", "revenue"}
    income = components["operating_income"]
    assert income.value == operating_income
    assert income.start_date == PERIOD_START
    assert income.end_date == PERIOD_END
    assert income.form == FORM
    assert income.accession_number == accession
    assert income.taxonomy == TAXONOMY
    assert income.concept == operating_income_concept
    assert income.source_url == source_url
    sales = components["revenue"]
    assert sales.value == revenue
    assert sales.start_date == PERIOD_START
    assert sales.end_date == PERIOD_END
    assert sales.form == FORM
    assert sales.accession_number == accession
    assert sales.taxonomy == TAXONOMY
    assert sales.concept == revenue_concept
    assert sales.source_url == source_url


GOOGLE_PRIOR_QUARTER_START = date(2025, 10, 1)
GOOGLE_PRIOR_QUARTER_END = date(2025, 12, 31)


class _CompareCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        if query != MSFT_GOOG_OPERATING_MARGINS_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return SimpleNamespace(
            intent=Intent.COMPARE,
            companies=["Microsoft", "Google"],
            metric="operating_margin",
        )


class _MismatchedPeriodFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        if company == "Microsoft":
            return _component_fact(
                company_name=MICROSOFT_NAME,
                ticker=MICROSOFT_TICKER,
                cik=MICROSOFT_CIK,
                metric=metric,
                value=(
                    MICROSOFT_OPERATING_INCOME
                    if metric == "operating_income"
                    else MICROSOFT_REVENUE
                ),
                start_date=PERIOD_START,
                end_date=PERIOD_END,
                accession_number=MICROSOFT_ACCESSION,
                concept=(
                    MICROSOFT_OPERATING_INCOME_CONCEPT
                    if metric == "operating_income"
                    else MICROSOFT_REVENUE_CONCEPT
                ),
                source_url=MICROSOFT_SOURCE_URL,
            )
        if company == "Google":
            return _component_fact(
                company_name=ALPHABET_NAME,
                ticker=ALPHABET_TICKER,
                cik=ALPHABET_CIK,
                metric=metric,
                value=(
                    ALPHABET_OPERATING_INCOME if metric == "operating_income" else ALPHABET_REVENUE
                ),
                start_date=GOOGLE_PRIOR_QUARTER_START,
                end_date=GOOGLE_PRIOR_QUARTER_END,
                accession_number=ALPHABET_ACCESSION,
                concept=(
                    ALPHABET_OPERATING_INCOME_CONCEPT
                    if metric == "operating_income"
                    else ALPHABET_REVENUE_CONCEPT
                ),
                source_url=ALPHABET_SOURCE_URL,
            )
        raise AssertionError(f"unexpected get_financials({company!r}, {metric!r})")


def _component_fact(
    *,
    company_name: str,
    ticker: str,
    cik: str,
    metric: str,
    value: Decimal,
    start_date: date,
    end_date: date,
    accession_number: str,
    concept: str,
    source_url: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        company_name=company_name,
        ticker=ticker,
        cik=cik,
        metric=metric,
        value=value,
        currency="USD",
        start_date=start_date,
        end_date=end_date,
        form=FORM,
        accession_number=accession_number,
        taxonomy=TAXONOMY,
        concept=concept,
        source_url=source_url,
    )


def test_run_turn_does_not_compute_margin_when_periods_mismatch() -> None:
    result = run_turn(
        MSFT_GOOG_OPERATING_MARGINS_QUERY,
        Runtime(completer=_CompareCompleter(), facts=_MismatchedPeriodFacts()),
    )

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.TABLE
    assert len(result.table_rows) == 2
    microsoft_margin = MICROSOFT_OPERATING_INCOME / MICROSOFT_REVENUE
    alphabet_margin = ALPHABET_OPERATING_INCOME / ALPHABET_REVENUE
    blended = (MICROSOFT_OPERATING_INCOME + ALPHABET_OPERATING_INCOME) / (
        MICROSOFT_REVENUE + ALPHABET_REVENUE
    )
    for row in result.table_rows:
        assert row.value is None
        assert row.reason == "period_mismatch"
        assert row.value != microsoft_margin
        assert row.value != alphabet_margin
        assert row.value != blended
    assert {row.cik for row in result.table_rows} == {MICROSOFT_CIK, ALPHABET_CIK}


class _ShareClassCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        return SimpleNamespace(
            intent=Intent.COMPARE,
            companies=["GOOG", "GOOGL"],
            metric="operating_margin",
        )


def test_run_turn_consolidates_goog_and_googl_to_one_alphabet_row() -> None:
    result = run_turn(
        "compare GOOG and GOOGL operating margins",
        Runtime(
            completer=_ShareClassCompleter(),
            facts=SecFactLookup(client=RecordedSECDataSource()),
        ),
    )

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.TABLE
    assert len(result.table_rows) == 1
    row = result.table_rows[0]
    assert row.cik == ALPHABET_CIK
    assert row.company_name == ALPHABET_NAME
    assert row.ticker == ALPHABET_TICKER
    assert row.metric == "operating_margin"
    assert row.value == ALPHABET_OPERATING_MARGIN


class _MissingMicrosoftFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        if company == "Microsoft":
            raise UnsupportedQuarterlyFactError(
                "No directly reported standalone-quarter fact exists for metric"
            )
        if company == "Google":
            return _component_fact(
                company_name=ALPHABET_NAME,
                ticker=ALPHABET_TICKER,
                cik=ALPHABET_CIK,
                metric=metric,
                value=(
                    ALPHABET_OPERATING_INCOME if metric == "operating_income" else ALPHABET_REVENUE
                ),
                start_date=PERIOD_START,
                end_date=PERIOD_END,
                accession_number=ALPHABET_ACCESSION,
                concept=(
                    ALPHABET_OPERATING_INCOME_CONCEPT
                    if metric == "operating_income"
                    else ALPHABET_REVENUE_CONCEPT
                ),
                source_url=ALPHABET_SOURCE_URL,
            )
        raise AssertionError(f"unexpected get_financials({company!r}, {metric!r})")


def test_run_turn_keeps_partial_compare_row_when_one_issuer_fact_is_missing() -> None:
    result = run_turn(
        MSFT_GOOG_OPERATING_MARGINS_QUERY,
        Runtime(completer=_CompareCompleter(), facts=_MissingMicrosoftFacts()),
    )

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.TABLE
    assert len(result.table_rows) == 2
    microsoft, alphabet = result.table_rows
    assert microsoft.value is None
    assert microsoft.reason == "missing_fact"
    assert alphabet.cik == ALPHABET_CIK
    assert alphabet.value == ALPHABET_OPERATING_MARGIN
    assert alphabet.reason is None


def test_run_turn_preserves_ambiguous_fact_reason_in_partial_compare_row() -> None:
    class _AmbiguousMicrosoftFacts(_MissingMicrosoftFacts):
        def get_financials(self, company: str, metric: str) -> SimpleNamespace:
            if company == "Microsoft":
                raise AmbiguousFactError("Supported concepts produced conflicting values")
            return super().get_financials(company, metric)

    result = run_turn(
        MSFT_GOOG_OPERATING_MARGINS_QUERY,
        Runtime(completer=_CompareCompleter(), facts=_AmbiguousMicrosoftFacts()),
    )

    microsoft, alphabet = result.table_rows
    assert microsoft.value is None
    assert microsoft.reason == "ambiguous_concept"
    assert alphabet.value == ALPHABET_OPERATING_MARGIN


class _ZeroRevenueFacts(_MissingMicrosoftFacts):
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        if company == "Microsoft":
            return _component_fact(
                company_name=MICROSOFT_NAME,
                ticker=MICROSOFT_TICKER,
                cik=MICROSOFT_CIK,
                metric=metric,
                value=(
                    MICROSOFT_OPERATING_INCOME
                    if metric == "operating_income"
                    else Decimal("0")
                ),
                start_date=PERIOD_START,
                end_date=PERIOD_END,
                accession_number=MICROSOFT_ACCESSION,
                concept=(
                    MICROSOFT_OPERATING_INCOME_CONCEPT
                    if metric == "operating_income"
                    else MICROSOFT_REVENUE_CONCEPT
                ),
                source_url=MICROSOFT_SOURCE_URL,
            )
        return super().get_financials(company, metric)


def test_run_turn_keeps_partial_compare_row_when_revenue_is_zero() -> None:
    result = run_turn(
        MSFT_GOOG_OPERATING_MARGINS_QUERY,
        Runtime(completer=_CompareCompleter(), facts=_ZeroRevenueFacts()),
    )

    microsoft, alphabet = result.table_rows
    assert microsoft.value is None
    assert microsoft.reason == "zero_denominator"
    assert [component.metric for component in microsoft.components] == [
        "operating_income",
        "revenue",
    ]
    assert alphabet.value == ALPHABET_OPERATING_MARGIN
    assert alphabet.reason is None


def test_run_turn_compare_does_not_pick_one_conflicting_concept() -> None:
    class _ConflictingMicrosoftFacts(_MissingMicrosoftFacts):
        def get_financials(self, company: str, metric: str) -> SimpleNamespace:
            if company == "Microsoft" and metric == "operating_income":
                raise AmbiguousFactError("Supported concepts produced conflicting values")
            return super().get_financials(company, metric)

    result = run_turn(
        MSFT_GOOG_OPERATING_MARGINS_QUERY,
        Runtime(completer=_CompareCompleter(), facts=_ConflictingMicrosoftFacts()),
    )

    assert result.renderer is RendererKind.TABLE
    microsoft, alphabet = result.table_rows
    assert microsoft.value is None
    assert microsoft.reason == "ambiguous_concept"
    assert alphabet.value == ALPHABET_OPERATING_MARGIN


def test_run_turn_refuses_unknown_compare_ratio_with_allowed_list() -> None:
    result = run_turn(UNKNOWN_RATIO_QUERY, fixture_runtime())

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.message is not None
    assert "roe" in result.message.casefold()
    for metric in ALLOWED_METRICS:
        assert metric in result.message


MSFT_GOOG_MARKET_CAP_QUERY = "compare Microsoft and Google market cap"
MICROSOFT_SNAPSHOT_MARKET_CAP = Decimal("3100000000000")
ALPHABET_SNAPSHOT_MARKET_CAP = Decimal("2200000000000")


def test_run_turn_compare_snapshot_market_caps() -> None:
    result = run_turn(MSFT_GOOG_MARKET_CAP_QUERY, fixture_runtime())

    assert result.intent is Intent.COMPARE
    assert result.renderer is RendererKind.TABLE
    microsoft, alphabet = result.table_rows
    assert microsoft.company_name == MICROSOFT_NAME
    assert microsoft.ticker == MICROSOFT_TICKER
    assert microsoft.cik == MICROSOFT_CIK
    assert microsoft.metric == "market_cap"
    assert microsoft.value == MICROSOFT_SNAPSHOT_MARKET_CAP
    assert microsoft.start_date is None
    assert alphabet.company_name == ALPHABET_NAME
    assert alphabet.ticker == ALPHABET_TICKER
    assert alphabet.value == ALPHABET_SNAPSHOT_MARKET_CAP
    assert result.tool_traces[0].tool == "compare_metrics"
    assert result.tool_traces[0].args == {
        "issuers": ["Microsoft", "Google"],
        "metric": "market_cap",
    }
