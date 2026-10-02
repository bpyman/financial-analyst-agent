"""A fiscal fourth quarter subtracts the nine months as the 10-K itself reports them."""

from datetime import date
from decimal import Decimal

import pytest

from sec_fixtures import fixture_lookup


@pytest.mark.parametrize(
    ("ticker", "metric", "year_end", "quarter", "ten_k"),
    [
        # Rapid7's 10-K revised nine months of net income from $27.0 M to $23.4 M:
        # the fourth quarter was a $2.2 M profit, not a $1.5 M loss.
        ("RPD", "net_income", date(2024, 12, 31), "2172000", "0001560327-25-000021"),
        ("CPAY", "operating_cash_flow", date(2023, 12, 31), "716502000", "0001628280-24-008060"),
        ("ALLY", "operating_cash_flow", date(2024, 12, 31), "951000000", "0000040729-25-000006"),
        ("MPWR", "net_income", date(2025, 12, 31), "171656000", "0001437749-26-006113"),
    ],
)
def test_the_nine_months_come_from_the_10_k_when_it_reports_them(
    ticker: str, metric: str, year_end: date, quarter: str, ten_k: str
) -> None:
    fact = fixture_lookup(ticker).get_financials(ticker, metric, report_date=year_end)

    assert fact.value == Decimal(quarter)
    assert fact.derivation is not None
    longer, shorter = fact.derivation.parts
    assert longer.accession_number == shorter.accession_number == ten_k
    assert shorter.form == "10-K"
