"""Pure deterministic filing selection by reporting period."""

from financial_analyst_agent.domain.enums import FormType
from financial_analyst_agent.domain.errors import FilingNotFoundError
from financial_analyst_agent.domain.models import Filing

_QUARTERLY_FORMS = frozenset({FormType.FORM_10_Q, FormType.FORM_10_Q_A})


def get_candidate_filings(filings: list[Filing]) -> list[Filing]:
    """
    Return filings for the newest report_date, ordered for fact-aware selection.

    Amendments (10-Q/A) are listed first by filed_date descending; original 10-Q
    filings follow as fallback. Never includes filings from older reporting
    periods.
    """
    quarterly = [filing for filing in filings if filing.form in _QUARTERLY_FORMS]
    if not quarterly:
        raise FilingNotFoundError(
            "No 10-Q or 10-Q/A filing found",
            details={"forms_seen": sorted({filing.form for filing in filings})},
        )

    newest_report_date = max(filing.report_date for filing in quarterly)
    for_period = [filing for filing in quarterly if filing.report_date == newest_report_date]
    if not for_period:
        raise FilingNotFoundError(
            "No valid 10-Q or 10-Q/A for newest reporting period",
            details={"report_date": newest_report_date.isoformat()},
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
