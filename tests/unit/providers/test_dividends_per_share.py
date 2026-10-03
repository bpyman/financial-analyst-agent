"""Dividends per share: paid before declared, and a quarter with none declared said so."""

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.domain.errors import PerShareNotDerivableError
from financial_analyst_agent.services.metric_catalog import get_concept_candidates, parse_metric
from sec_fixtures import fixture_lookup


def test_the_dividend_paid_comes_before_the_one_declared() -> None:
    candidates = get_concept_candidates(parse_metric("dividends_per_share"))
    concepts = [concept for _, concept in candidates]

    assert concepts.index("CommonStockDividendsPerShareCashPaid") < concepts.index(
        "CommonStockDividendsPerShareDeclared"
    )


def test_a_quarter_after_the_year_s_dividend_was_declared_is_not_zero() -> None:
    # Walmart declares the year's dividend in its first quarter; the second
    # quarter's declared $0.00 is not a dividend cut.
    lookup = fixture_lookup("WMT")

    with pytest.raises(PerShareNotDerivableError):
        lookup.get_financials("WMT", "dividends_per_share", report_date=date(2026, 7, 31))
    first = lookup.get_financials("WMT", "dividends_per_share", report_date=date(2026, 4, 30))
    assert first.value == Decimal("0.99")


def test_a_quarter_with_no_dividend_says_so_without_guessing_why() -> None:
    from financial_analyst_agent.domain.errors import NoDividendThisQuarterError
    from financial_analyst_agent.presentation import format_reason
    from financial_analyst_agent.turn import _per_share_reason

    lookup = fixture_lookup("WMT")
    with pytest.raises(NoDividendThisQuarterError) as raised:
        lookup.get_financials("WMT", "dividends_per_share", report_date=date(2026, 7, 31))

    # The filing reads the same for a year's dividend declared at once and for
    # a suspension, so neither "reported for the year" nor "declared earlier".
    assert format_reason(_per_share_reason(raised.value)) == "No dividend declared this quarter"
    assert "declared earlier in the fiscal year" in str(raised.value)
