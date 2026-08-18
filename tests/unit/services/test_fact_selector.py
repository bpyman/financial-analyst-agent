"""Fact selector tests."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import AmbiguousFactError, UnsupportedQuarterlyFactError
from financial_analyst_agent.services.fact_selector import select_quarterly_fact
from helpers import make_fact, make_filing

FILING = make_filing()
SOURCE_URL = "https://www.sec.gov/Archives/edgar/data/320193/aapl.htm"
COMPANY = {
    "company_name": "Apple Inc.",
    "ticker": "AAPL",
    "cik": "0000320193",
}
REPORT_END = date(2024, 9, 28)


def _select(facts: list, filing=FILING) -> object:
    selected = select_quarterly_fact(
        facts,
        filing,
        Metric.NET_INCOME,
        "USD",
        source_url=SOURCE_URL,
        **COMPANY,
    )
    assert len(selected) == 1
    return selected[0]


def test_selects_standalone_quarterly_fact() -> None:
    result = _select([make_fact(value=Decimal("23636000000"))])
    assert result.value == Decimal("23636000000")
    assert result.directly_reported is True
    assert result.source.value == "sec_xbrl"
    assert result.metric == Metric.NET_INCOME
    assert result.concept == "NetIncomeLoss"


def test_rejects_ytd_fact_same_accession() -> None:
    facts = [
        make_fact(
            start_date=date(2023, 10, 1),
            end_date=REPORT_END,
            value=Decimal("50000000000"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_rejects_comparative_prior_year_same_accession() -> None:
    facts = [
        make_fact(
            start_date=date(2023, 7, 2),
            end_date=date(2023, 9, 30),
            value=Decimal("22956000000"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_rejects_wrong_accession() -> None:
    facts = [
        make_fact(
            accession_number="0000320193-24-000050",
            value=Decimal("100"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_rejects_wrong_unit() -> None:
    facts = [make_fact(unit="EUR", value=Decimal("100"))]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_rejects_instant_fact_without_duration() -> None:
    facts = [make_fact(start_date=None, value=Decimal("100"))]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_selects_current_quarter_among_mixed_facts() -> None:
    facts = [
        make_fact(
            start_date=date(2023, 10, 1),
            end_date=REPORT_END,
            value=Decimal("50000000000"),
        ),
        make_fact(
            start_date=date(2023, 7, 2),
            end_date=date(2023, 9, 30),
            value=Decimal("22956000000"),
        ),
        make_fact(
            start_date=date(2024, 6, 30),
            end_date=REPORT_END,
            value=Decimal("23636000000"),
        ),
    ]
    result = _select(facts)
    assert result.value == Decimal("23636000000")


def test_ambiguous_when_multiple_same_filed_date() -> None:
    facts = [
        make_fact(value=Decimal("100")),
        make_fact(value=Decimal("200")),
    ]
    with pytest.raises(AmbiguousFactError):
        _select(facts)


def test_prefers_latest_filed_date_on_restatement() -> None:
    facts = [
        make_fact(filed_date=date(2024, 11, 1), value=Decimal("23636000000")),
        make_fact(filed_date=date(2024, 12, 15), value=Decimal("23650000000")),
    ]
    result = _select(facts)
    assert result.value == Decimal("23650000000")


def test_10_q_filing_rejects_only_10_q_a_facts_on_incompatible_accession() -> None:
    facts = [
        make_fact(
            form="10-Q/A",
            accession_number="0000320193-24-000082",
            value=Decimal("100"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_10_q_filing_rejects_same_accession_10_q_a_form() -> None:
    facts = [
        make_fact(
            form="10-Q/A",
            accession_number=FILING.accession_number,
            value=Decimal("100"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_10_q_a_filing_requires_10_q_a_form_on_fact() -> None:
    amendment_filing = make_filing(
        form="10-Q/A",
        accession_number="0000320193-24-000082",
    )
    facts = [
        make_fact(
            form="10-Q",
            accession_number="0000320193-24-000082",
            value=Decimal("100"),
        ),
        make_fact(
            form="10-Q/A",
            accession_number="0000320193-24-000082",
            value=Decimal("200"),
        ),
    ]
    result = select_quarterly_fact(
        facts,
        amendment_filing,
        Metric.NET_INCOME,
        "USD",
        source_url=SOURCE_URL,
        **COMPANY,
    )
    assert len(result) == 1
    assert result[0].value == Decimal("200")
    assert result[0].form == "10-Q/A"


def test_matching_concepts_return_highest_priority() -> None:
    shared_value = Decimal("23636000000")
    facts = [
        make_fact(concept="NetIncomeLoss", value=shared_value),
        make_fact(concept="ProfitLoss", value=shared_value),
    ]
    result = _select(facts)
    assert result.concept == "NetIncomeLoss"
    assert result.value == shared_value


def test_conflicting_concepts_raise_ambiguous_fact_error() -> None:
    facts = [
        make_fact(concept="NetIncomeLoss", value=Decimal("23636000000")),
        make_fact(concept="ProfitLoss", value=Decimal("999")),
    ]
    with pytest.raises(AmbiguousFactError) as exc_info:
        _select(facts)
    details = exc_info.value.details
    assert details["metric"] == "net_income"
    assert len(details["concepts"]) == 2


def test_duration_70_days_accepted() -> None:
    start = REPORT_END - timedelta(days=70)
    result = _select([make_fact(start_date=start, end_date=REPORT_END, value=Decimal("1"))])
    assert result.value == Decimal("1")


def test_duration_110_days_accepted() -> None:
    start = REPORT_END - timedelta(days=110)
    result = _select([make_fact(start_date=start, end_date=REPORT_END, value=Decimal("2"))])
    assert result.value == Decimal("2")


def test_duration_69_days_rejected() -> None:
    start = REPORT_END - timedelta(days=69)
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select([make_fact(start_date=start, end_date=REPORT_END, value=Decimal("3"))])


def test_duration_111_days_rejected() -> None:
    start = REPORT_END - timedelta(days=111)
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select([make_fact(start_date=start, end_date=REPORT_END, value=Decimal("4"))])
