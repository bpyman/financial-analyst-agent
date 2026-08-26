"""Filing selector tests — latest and named reporting periods."""

from datetime import date

import pytest

from financial_analyst_agent.domain.errors import FilingNotFoundError
from financial_analyst_agent.services.filing_selector import get_candidate_filings
from helpers import make_filing

NEWER = date(2024, 9, 28)
OLDER = date(2024, 6, 29)


def test_latest_selects_newest_report_date_only() -> None:
    filings = [
        make_filing(
            accession_number="0000320193-24-000060",
            report_date=OLDER,
            filed_date=date(2024, 8, 1),
        ),
        make_filing(
            accession_number="0000320193-24-000081",
            report_date=NEWER,
            filed_date=date(2024, 11, 1),
        ),
    ]

    candidates = get_candidate_filings(filings)

    assert [f.report_date for f in candidates] == [NEWER]
    assert candidates[0].accession_number == "0000320193-24-000081"


def test_named_report_date_selects_that_period_not_latest() -> None:
    filings = [
        make_filing(
            accession_number="0000320193-24-000060",
            report_date=OLDER,
            filed_date=date(2024, 8, 1),
            primary_document="aapl-20240629.htm",
        ),
        make_filing(
            accession_number="0000320193-24-000081",
            report_date=NEWER,
            filed_date=date(2024, 11, 1),
        ),
    ]

    candidates = get_candidate_filings(filings, report_date=OLDER)

    assert len(candidates) == 1
    assert candidates[0].report_date == OLDER
    assert candidates[0].accession_number == "0000320193-24-000060"


def test_named_report_date_missing_is_typed_failure_not_nearest() -> None:
    filings = [
        make_filing(report_date=NEWER),
        make_filing(
            accession_number="0000320193-24-000060",
            report_date=OLDER,
            filed_date=date(2024, 8, 1),
        ),
    ]

    with pytest.raises(FilingNotFoundError) as exc_info:
        get_candidate_filings(filings, report_date=date(2024, 3, 30))

    assert date(2024, 3, 30).isoformat() in str(exc_info.value.details.get("report_date", ""))


def test_named_report_date_prefers_amendment_then_original() -> None:
    filings = [
        make_filing(
            form="10-Q",
            accession_number="0000320193-24-000060",
            report_date=OLDER,
            filed_date=date(2024, 8, 1),
        ),
        make_filing(
            form="10-Q/A",
            accession_number="0000320193-24-000061",
            report_date=OLDER,
            filed_date=date(2024, 8, 15),
        ),
    ]

    candidates = get_candidate_filings(filings, report_date=OLDER)

    assert [f.accession_number for f in candidates] == [
        "0000320193-24-000061",
        "0000320193-24-000060",
    ]
