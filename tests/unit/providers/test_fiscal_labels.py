"""A named fiscal quarter finds one period even when a filer declares a label twice."""

from datetime import date

import pytest

from financial_analyst_agent.services.fiscal_periods import dates_for
from sec_fixtures import fixture_lookup


@pytest.mark.parametrize(
    ("ticker", "year", "quarter", "end"),
    [
        # Salesforce's 10-K for the year ended January 31, 2026 declares fiscal 2025.
        ("CRM", 2026, 4, date(2026, 1, 31)),
        ("CRM", 2025, 4, date(2025, 1, 31)),
        # Blackstone's second-quarter 10-Q of 2024 declares Q1.
        ("BX", 2024, 1, date(2024, 3, 31)),
        ("BX", 2024, 2, date(2024, 6, 30)),
        # CrowdStrike's 10-Ks declare the year before, and one 10-Q its last year.
        ("CRWD", 2025, 4, date(2025, 1, 31)),
        ("CRWD", 2026, 1, date(2025, 4, 30)),
        ("CRWD", 2025, 1, date(2024, 4, 30)),
        # Freeport's 10-K for 2024 declares 2023.
        ("FCX", 2024, 4, date(2024, 12, 31)),
        ("FCX", 2023, 4, date(2023, 12, 31)),
        # Dell's first two 10-Qs of fiscal 2024 declare a full year.
        ("DELL", 2024, 1, date(2023, 5, 5)),
        ("DELL", 2024, 2, date(2023, 8, 4)),
        ("DELL", 2024, 4, date(2024, 2, 2)),
    ],
)
def test_a_duplicated_label_is_rederived_from_the_quarter_s_position(
    ticker: str, year: int, quarter: int, end: date
) -> None:
    periods = fixture_lookup(ticker).fiscal_periods(ticker)

    assert dates_for(periods, year, quarter, calendar=False) == (end,)


def test_no_two_periods_share_a_label_after_the_repair() -> None:
    for ticker in ("CRM", "BX", "CRWD", "FCX", "DELL"):
        periods = fixture_lookup(ticker).fiscal_periods(ticker)
        labels = [(period.fiscal_year, period.quarter) for period in periods]
        assert len(labels) == len(set(labels)), ticker
