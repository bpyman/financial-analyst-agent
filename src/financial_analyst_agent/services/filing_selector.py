"""Pure deterministic filing selection by reporting period."""

from datetime import date, timedelta

from financial_analyst_agent.domain.enums import ANNUAL_FORMS, QUARTERLY_FORMS, FormType
from financial_analyst_agent.domain.errors import FilingNotFoundError
from financial_analyst_agent.domain.models import Filing

# A 52/53-week fiscal quarter ends on a weekday up to six days from the calendar
# quarter end (Apple's March 28 against Microsoft's March 31), never a neighbouring
# quarter, which ends about 90 days away.
FISCAL_WEEK_TOLERANCE = timedelta(days=6)


def get_candidate_filings(
    filings: list[Filing],
    *,
    report_date: date | None = None,
) -> list[Filing]:
    """
    Return filings for one reporting period, ordered for fact-aware selection.

    When ``report_date`` is omitted, the newest report_date is used. When it is
    set, only that period is considered — never a neighbouring quarter. A filer
    on a 52/53-week calendar reports the same quarter a few days off the named
    date, so with no exact match the nearest report_date within
    ``FISCAL_WEEK_TOLERANCE`` stands for it.
    Amendments (10-Q/A) are listed first by filed_date descending; original 10-Q
    filings follow as fallback.
    """
    quarterly = [filing for filing in filings if filing.form in QUARTERLY_FORMS]
    if not quarterly:
        raise FilingNotFoundError(
            "No 10-Q or 10-Q/A filing found",
            details={"forms_seen": sorted({filing.form for filing in filings})},
        )

    target = (
        report_date
        if report_date is not None
        else max(filing.report_date for filing in quarterly)
    )
    for_period = [filing for filing in quarterly if filing.report_date == target]
    if not for_period and report_date is not None:
        near = [
            filing
            for filing in quarterly
            if abs(filing.report_date - target) <= FISCAL_WEEK_TOLERANCE
        ]
        if near:
            nearest = min(abs(filing.report_date - target) for filing in near)
            for_period = [
                filing for filing in near if abs(filing.report_date - target) == nearest
            ]
    if not for_period:
        raise FilingNotFoundError(
            "No valid 10-Q or 10-Q/A for reporting period",
            details={"report_date": target.isoformat()},
        )

    amendments = sorted(
        [filing for filing in for_period if filing.form == FormType.FORM_10_Q_A],
        key=lambda filing: filing.filed_date,
        reverse=True,
    )
    originals = sorted(
        [filing for filing in for_period if filing.form == FormType.FORM_10_Q],
        key=lambda filing: filing.filed_date,
        reverse=True,
    )
    return amendments + originals


def get_annual_filings(filings: list[Filing], *, report_date: date) -> list[Filing]:
    """10-K / 10-K/A filings for one fiscal year end, amendments first.

    Like ``get_candidate_filings``, a 52/53-week year end a few days off the
    named date stands for it; an empty list means no 10-K covers the date.
    """
    annual = [
        filing
        for filing in filings
        if filing.form in ANNUAL_FORMS
        and abs(filing.report_date - report_date) <= FISCAL_WEEK_TOLERANCE
    ]
    if not annual:
        return []
    nearest = min(abs(filing.report_date - report_date) for filing in annual)
    annual = [filing for filing in annual if abs(filing.report_date - report_date) == nearest]
    return sorted(
        annual,
        key=lambda filing: (filing.form == FormType.FORM_10_K_A, filing.filed_date),
        reverse=True,
    )


def latest_period_end(filings: list[Filing]) -> date | None:
    """The newest period any 10-Q or 10-K covers."""
    ends = [
        filing.report_date
        for filing in filings
        if filing.form in QUARTERLY_FORMS or filing.form in ANNUAL_FORMS
    ]
    return max(ends) if ends else None


def list_quarterly_report_dates(
    filings: list[Filing],
    *,
    limit: int,
) -> list[date]:
    """Newest-first distinct quarter ends, up to ``limit``.

    A 10-K's year end is the fiscal fourth quarter's end, so it is listed
    beside the 10-Q dates (ADR 0007).
    """
    if limit < 1:
        return []
    periodic = [
        filing
        for filing in filings
        if filing.form in QUARTERLY_FORMS or filing.form in ANNUAL_FORMS
    ]
    unique: list[date] = []
    for day in sorted({filing.report_date for filing in periodic}, reverse=True):
        # A 10-K/A dated a day off its 10-K is the same period, not a new quarter.
        if unique and unique[-1] - day <= FISCAL_WEEK_TOLERANCE:
            continue
        unique.append(day)
    return unique[:limit]
