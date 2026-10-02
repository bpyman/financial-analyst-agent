"""Which revenue line is the total: real filers whose first catalog concept is not."""

from datetime import date
from decimal import Decimal

from tests.sec_fixtures import fixture_lookup


def test_a_component_line_tagged_revenues_gives_way_to_the_total() -> None:
    # Verra Mobility tags one segment's $25.8 M as Revenues; its costs and
    # expenses plus operating income add up to the contract revenue instead.
    fact = fixture_lookup("VRRM").get_financials(
        "VRRM", "revenue", report_date=date(2026, 6, 30)
    )

    assert fact.value == Decimal("263591000")
    assert fact.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert fact.directly_reported


def test_operating_expenses_plus_operating_income_confirm_the_total() -> None:
    # Kopin tags no costs-and-expenses total; its operating expenses include cost of sales.
    fact = fixture_lookup("KOPN").get_financials(
        "KOPN", "revenue", report_date=date(2026, 6, 27)
    )

    assert fact.value == Decimal("12734434")


def test_a_derived_fourth_quarter_reads_the_total_in_both_filings() -> None:
    # Alliance Entertainment's Revenues is $2.7 M for a year with $27 M of
    # operating income; the fourth quarter was $500,000 against about $1.1 B a year.
    fact = fixture_lookup("AENT").get_financials(
        "AENT", "revenue", report_date=date(2026, 6, 30)
    )

    assert fact.value == Decimal("268100000")
    assert fact.derivation is not None
    assert {part.concept for part in fact.derivation.parts} == {
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    }


def test_a_smaller_revenues_that_the_identity_confirms_is_kept() -> None:
    # California Resources' Revenues nets a derivative loss off its oil sales:
    # $119 M is right, and costs and expenses plus operating income agree.
    lookup = fixture_lookup("CRC")

    first = lookup.get_financials("CRC", "revenue", report_date=date(2026, 3, 31))
    second = lookup.get_financials("CRC", "revenue", report_date=date(2026, 6, 30))

    assert (first.value, first.concept) == (Decimal("119000000"), "Revenues")
    assert second.value == Decimal("1297000000")


def test_a_bank_s_revenue_is_net_interest_income_plus_noninterest_income() -> None:
    # M&T tags neither Revenues nor net revenue; its contract revenue is fee income only.
    fact = fixture_lookup("MTB").get_financials("MTB", "revenue", report_date=date(2026, 6, 30))

    assert fact.value == Decimal("2532000000")
    assert fact.derivation is not None
    assert [part.concept for part in fact.derivation.parts] == [
        "InterestIncomeExpenseNet",
        "NoninterestIncome",
    ]


def test_huntington_s_revenue_is_its_net_interest_and_noninterest_income() -> None:
    fact = fixture_lookup("HBAN").get_financials("HBAN", "revenue", report_date=date(2026, 3, 31))

    assert fact.value == Decimal("2573000000")


def test_gross_profit_leaves_out_membership_and_other_income() -> None:
    # Walmart's Revenues adds $1.8 B of membership and other income to net sales;
    # gross profit is net sales minus cost of sales.
    fact = fixture_lookup("WMT").get_financials(
        "WMT", "gross_profit", report_date=date(2026, 7, 31)
    )

    assert fact.value == Decimal("186100000000") - Decimal("138804000000")
