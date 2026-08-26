"""Pure deterministic filing selection by reporting period."""

from datetime import date

from financial_analyst_agent.domain.enums import FormType
from financial_analyst_agent.domain.errors import FilingNotFoundError
from financial_analyst_agent.domain.models import Filing

_QUARTERLY_FORMS = frozenset({FormType.FORM_10_Q, FormType.FORM_10_Q_A})


def get_candidate_filings(
    filings: list[Filing],
    *,
    report_date: date | None = None,
) -> list[Filing]:
    """
    Return filings for one reporting period, ordered for fact-aware selection.

    When ``report_date`` is omitted, the newest report_date is used. When it is
    set, only that period is considered — never a neighbouring quarter.
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
