"""Pure deterministic filing selection by reporting period."""

from datetime import date, timedelta

from financial_analyst_agent.domain.enums import FormType
from financial_analyst_agent.domain.errors import FilingNotFoundError
from financial_analyst_agent.domain.models import Filing

_QUARTERLY_FORMS = frozenset({FormType.FORM_10_Q, FormType.FORM_10_Q_A})
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
    quarterly = [filing for filing in filings if filing.form in _QUARTERLY_FORMS]
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


def list_quarterly_report_dates(
    filings: list[Filing],
    *,
    limit: int,
) -> list[date]:
    """Newest-first distinct 10-Q / 10-Q/A report dates, up to ``limit``."""
    if limit < 1:
        return []
    quarterly = [filing for filing in filings if filing.form in _QUARTERLY_FORMS]
    unique = sorted({filing.report_date for filing in quarterly}, reverse=True)
    return unique[:limit]
