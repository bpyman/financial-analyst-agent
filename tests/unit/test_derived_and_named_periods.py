"""Derived quarters, per-share figures and named periods (ADR 0007)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import (
    PerShareNotDerivableError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import FactRecord, Filing
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    NamedPeriodSpec,
    PeriodSelection,
    ResolvedCompany,
    compile_tasks,
)
from financial_analyst_agent.graph.spec_turn import bind_periods_from_message, parse_named_periods
from financial_analyst_agent.presentation import format_metric_value, present_turn
from financial_analyst_agent.services.fact_selector import (
    FOURTH_QUARTER_LABEL,
    YEAR_TO_DATE_LABEL,
    derive_quarter,
)
from financial_analyst_agent.services.filing_selector import list_quarterly_report_dates
from financial_analyst_agent.services.fiscal_periods import (
    FiscalLabel,
    calendar_quarter,
    dates_for,
    periods_from_filings,
)
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase

FY_START = date(2024, 9, 29)
Q1_END = date(2024, 12, 28)
Q2_END = date(2025, 3, 29)
Q3_END = date(2025, 6, 28)
FY_END = date(2025, 9, 27)


def _fact(
    concept: str,
    start: date,
    end: date,
    value: str,
    accession: str,
    form: str = "10-Q",
    unit: str = "USD",
) -> FactRecord:
    return FactRecord(
        accession_number=accession,
        start_date=start,
        end_date=end,
        form=form,
        unit=unit,
        value=Decimal(value),
        concept=concept,
        taxonomy="us-gaap",
        filed_date=end.replace(day=1) if end.month == 12 else date(end.year, end.month + 1, 1),
    )


def _filing(form: str, accession: str, report_date: date) -> Filing:
    return Filing(
        form=form,
        accession_number=accession,
        filed_date=report_date,
        report_date=report_date,
    )


def _derive(facts: list[FactRecord], filing: Filing, metric: Metric, unit: str = "USD"):  # type: ignore[no-untyped-def]
    return derive_quarter(
        facts,
        filing,
        metric,
        unit,
        "Apple Inc.",
        "AAPL",
        "0000320193",
        "https://www.sec.gov/primary.htm",
        lambda accession: f"https://www.sec.gov/{accession}.htm",
    )


REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"
CASH = "NetCashProvidedByUsedInOperatingActivities"


def test_fourth_quarter_is_the_year_minus_nine_months() -> None:
    facts = [
        _fact(REVENUE, FY_START, Q3_END, "313695", "q3", "10-Q"),
        _fact(REVENUE, date(2025, 3, 30), Q3_END, "94036", "q3", "10-Q"),
        _fact(REVENUE, FY_START, FY_END, "416161", "k", "10-K"),
    ]

    fact = _derive(facts, _filing("10-K", "k", FY_END), Metric.REVENUE)

    assert fact.value == Decimal("102466")
    assert (fact.start_date, fact.end_date) == (date(2025, 6, 29), FY_END)
    assert fact.directly_reported is False
    assert fact.derivation is not None
    assert fact.derivation.label == FOURTH_QUARTER_LABEL
    assert [part.accession_number for part in fact.derivation.parts] == ["k", "q3"]
    assert fact.derivation.parts[1].source_url == "https://www.sec.gov/q3.htm"


def test_a_standalone_fourth_quarter_in_the_10k_is_used_as_reported() -> None:
    facts = [
        _fact(REVENUE, FY_START, FY_END, "416161", "k", "10-K"),
        _fact(REVENUE, date(2025, 6, 29), FY_END, "102466", "k", "10-K"),
    ]

    fact = _derive(facts, _filing("10-K", "k", FY_END), Metric.REVENUE)

    assert fact.value == Decimal("102466")
    assert fact.directly_reported is True
    assert fact.derivation is None


def test_cash_flow_quarter_is_year_to_date_minus_the_previous_quarter() -> None:
    facts = [
        _fact(CASH, FY_START, Q1_END, "29935", "q1"),
        _fact(CASH, FY_START, Q2_END, "53887", "q2"),
    ]

    fact = _derive(facts, _filing("10-Q", "q2", Q2_END), Metric.OPERATING_CASH_FLOW)

    assert fact.value == Decimal("23952")
    assert fact.start_date == date(2024, 12, 29)
    assert fact.derivation is not None and fact.derivation.label == YEAR_TO_DATE_LABEL


def test_amounts_with_different_start_dates_are_never_subtracted() -> None:
    facts = [
        _fact(CASH, date(2024, 10, 1), Q1_END, "29935", "q1"),
        _fact(CASH, FY_START, Q2_END, "53887", "q2"),
    ]

    with pytest.raises(UnsupportedQuarterlyFactError):
        _derive(facts, _filing("10-Q", "q2", Q2_END), Metric.OPERATING_CASH_FLOW)


def test_fourth_quarter_eps_is_never_derived() -> None:
    concept = "EarningsPerShareDiluted"
    facts = [
        _fact(concept, FY_START, Q3_END, "5.62", "q3", unit="USD/shares"),
        _fact(concept, FY_START, FY_END, "7.46", "k", "10-K", unit="USD/shares"),
    ]

    with pytest.raises(PerShareNotDerivableError):
        _derive(facts, _filing("10-K", "k", FY_END), Metric.EPS_DILUTED, "USD/shares")


def test_windows_list_the_10k_year_end_as_a_quarter() -> None:
    filings = [
        _filing("10-Q", "q3", Q3_END),
        _filing("10-K", "k", FY_END),
        _filing("10-K/A", "ka", date(2025, 9, 28)),
        _filing("10-Q", "q2", Q2_END),
    ]

    assert list_quarterly_report_dates(filings, limit=3) == [date(2025, 9, 28), Q3_END, Q2_END]


def test_metric_phrases_name_eps_and_cash_flow() -> None:
    def metric(question: str) -> str | None:
        return resolve_metric_phrase(question).metric

    assert metric("Apple EPS") == "eps_diluted"
    assert metric("earnings per share for Apple") == "eps_diluted"
    assert metric("basic EPS") == "eps_basic"
    assert metric("Microsoft free cash flow") == "free_cash_flow"
    assert metric("capex at Amazon") == "capital_expenditure"
    assert metric("cash from operations") == "operating_cash_flow"
    assert resolve_metric_phrase("Apple cash flow").kind == "ambiguous"


def test_per_share_amounts_show_cents() -> None:
    assert format_metric_value("eps_diluted", Decimal("2.02")) == "$2.02"
    assert format_metric_value("eps_diluted", Decimal("-0.155")) == "-$0.16"
    assert format_metric_value("free_cash_flow", Decimal("19640000000")) == "$19.64 B"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Apple revenue Q3 2024", [NamedPeriodSpec(year=2024, quarter=3)]),
        ("Nvidia margin in Q3 FY25", [NamedPeriodSpec(year=2025, quarter=3)]),
        ("revenue 2024 Q1", [NamedPeriodSpec(year=2024, quarter=1)]),
        ("third quarter of fiscal 2024", [NamedPeriodSpec(year=2024, quarter=3)]),
        ("Nvidia net income fiscal 2025", [NamedPeriodSpec(year=2025)]),
        ("FY24 revenue", [NamedPeriodSpec(year=2024)]),
        (
            "Walmart revenue calendar Q1 2026",
            [NamedPeriodSpec(year=2026, quarter=1, calendar=True)],
        ),
        ("Apple revenue in 2023", [NamedPeriodSpec(year=2023)]),
        (
            "Q3 2024 vs Q3 2023",
            [NamedPeriodSpec(year=2024, quarter=3), NamedPeriodSpec(year=2023, quarter=3)],
        ),
        ("revenue for the last 4 quarters", []),
        ("top 5 banks", []),
    ],
)
def test_named_periods_are_read_from_the_question(
    question: str, expected: list[NamedPeriodSpec]
) -> None:
    assert list(parse_named_periods(question)) == expected


def test_a_named_quarter_with_growth_wording_adds_the_year_earlier() -> None:
    from financial_analyst_agent.graph.analysis_spec import SpecPatch

    patch = bind_periods_from_message(SpecPatch(mode="replace"), "Apple revenue Q4 2025 yoy")

    assert patch.set_periods is not None
    assert patch.set_periods.named == (
        NamedPeriodSpec(year=2025, quarter=4),
        NamedPeriodSpec(year=2024, quarter=4),
    )
    assert "across_periods" in patch.add_operations


def test_fiscal_and_calendar_quarters_come_from_each_filing() -> None:
    filings = [
        _filing("10-Q", "q3", Q3_END),
        _filing("10-K", "k", FY_END),
        _filing("10-Q", "q2", Q2_END),
    ]
    labels = {
        "q3": FiscalLabel(2025, "Q3"),
        "q2": FiscalLabel(2025, "Q2"),
        "k": FiscalLabel(2025, "FY"),
    }
    periods = periods_from_filings(filings, labels)

    assert dates_for(periods, 2025, 3, calendar=False) == (Q3_END,)
    assert dates_for(periods, 2025, 4, calendar=False) == (FY_END,)
    assert dates_for(periods, 2025, None, calendar=False) == (FY_END, Q3_END, Q2_END)
    assert calendar_quarter(date(2025, 10, 26)) == (2025, 3)
    assert dates_for(periods, 2025, 2, calendar=True) == (Q3_END,)


def test_a_named_quarter_asks_each_company_for_its_own_quarter_end() -> None:
    apple = ResolvedCompany(cik="1", name="Apple Inc.", ticker="AAPL", query="AAPL")
    microsoft = ResolvedCompany(cik="2", name="Microsoft", ticker="MSFT", query="MSFT")
    spec = AnalysisSpec(
        companies=(apple, microsoft),
        metrics=("revenue",),
        periods=PeriodSelection(
            kind="named",
            named=(NamedPeriodSpec(year=2024, quarter=3),),
            report_dates=(date(2024, 6, 29),),
            count=1,
            company_report_dates=(
                ("aapl", (date(2024, 6, 29),)),
                ("msft", (date(2024, 3, 31),)),
            ),
        ),
        operations=("across_companies",),
    )

    tasks = compile_tasks(spec)

    assert {(task.company_queries, task.report_date) for task in tasks} == {
        (("AAPL",), date(2024, 6, 29)),
        (("MSFT",), date(2024, 3, 31)),
    }


def test_derived_values_are_marked_and_explained() -> None:
    row = TableRow(
        company_name="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        metric="revenue",
        value=Decimal("102466000000"),
        start_date=date(2025, 6, 29),
        end_date=FY_END,
        derivation=FOURTH_QUARTER_LABEL,
    )
    other = row.model_copy(update={"derivation": None, "end_date": Q3_END})
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        table_rows=[row, other],
        tool_traces=[],
    )

    presented = present_turn(result)

    assert presented.table is not None
    values = [r[presented.table.keys.index("value:revenue")] for r in presented.table.rows]
    assert values == ["$102.47 B †", "$102.47 B"]
    assert any("10-K's full year minus the 10-Q's nine months" in b for b in presented.banners)
