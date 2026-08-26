"""Pure deterministic quarterly fact selection from normalized XBRL records."""

from collections.abc import Callable
from datetime import date

from financial_analyst_agent.domain.enums import DataSourceKind, FormType, Metric
from financial_analyst_agent.domain.errors import (
    AmbiguousFactError,
    FilingNotFoundError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import FactRecord, Filing, FinancialFact
from financial_analyst_agent.services.filing_selector import get_candidate_filings
from financial_analyst_agent.services.metric_catalog import get_concept_candidates

_QUARTERLY_FORMS = frozenset({FormType.FORM_10_Q, FormType.FORM_10_Q_A})
_MIN_QUARTER_DAYS = 70
_MAX_QUARTER_DAYS = 110


def _duration_days(start: date, end: date) -> int:
    return (end - start).days


def _is_quarterly_form(form: str, selected_form: str) -> bool:
    if form not in _QUARTERLY_FORMS:
        return False
    return form == selected_form


def _is_standalone_quarter_duration(start_date: date | None, end_date: date) -> bool:
    if start_date is None:
        return False
    days = _duration_days(start_date, end_date)
    return _MIN_QUARTER_DAYS <= days <= _MAX_QUARTER_DAYS


def _filter_quarterly_candidates(
    facts: list[FactRecord],
    filing: Filing,
    taxonomy: str,
    concept: str,
    currency: str,
) -> list[FactRecord]:
    """Apply all mandatory filters; reject YTD, comparative, and instant facts."""
    candidates: list[FactRecord] = []
    for fact in facts:
        if fact.taxonomy != taxonomy or fact.concept != concept:
            continue
        if fact.accession_number != filing.accession_number:
            continue
        if fact.end_date != filing.report_date:
            continue
        if not _is_quarterly_form(fact.form, filing.form):
            continue
        if fact.unit.upper() != currency.upper():
            continue
        if not _is_standalone_quarter_duration(fact.start_date, fact.end_date):
            continue
        candidates.append(fact)
    return candidates


def _resolve_same_concept_candidates(candidates: list[FactRecord]) -> FactRecord:
    """Apply same-concept precedence; error if multiple remain at same filed_date."""
    if len(candidates) == 1:
        return candidates[0]

    by_filed = sorted(candidates, key=lambda fact: fact.filed_date, reverse=True)
    best_filed = by_filed[0].filed_date
    top = [fact for fact in by_filed if fact.filed_date == best_filed]
    if len(top) == 1:
        return top[0]

    raise AmbiguousFactError(
        "Multiple directly reported quarterly facts remain after precedence rules",
        details={
            "candidates": [
                {
                    "accession_number": fact.accession_number,
                    "concept": fact.concept,
                    "start_date": fact.start_date.isoformat() if fact.start_date else None,
                    "end_date": fact.end_date.isoformat(),
                    "filed_date": fact.filed_date.isoformat(),
                    "value": str(fact.value),
                }
                for fact in top
            ],
        },
    )


def _build_financial_fact(
    selected: FactRecord,
    metric: Metric,
    currency: str,
    company_name: str,
    ticker: str,
    cik: str,
    source_url: str,
) -> FinancialFact:
    if selected.start_date is None:
        raise UnsupportedQuarterlyFactError(
            "Selected fact missing start_date for quarterly duration",
            details={"concept": selected.concept},
        )
    return FinancialFact(
        company_name=company_name,
        ticker=ticker,
        cik=cik,
        metric=metric,
        value=selected.value,
        currency=currency.upper(),
        start_date=selected.start_date,
        end_date=selected.end_date,
        form=selected.form,
        filed_date=selected.filed_date,
        accession_number=selected.accession_number,
        taxonomy=selected.taxonomy,
        concept=selected.concept,
        source_url=source_url,
        directly_reported=True,
        source=DataSourceKind.SEC_XBRL,
    )


def select_quarterly_fact(
    facts: list[FactRecord],
    filing: Filing,
    metric: Metric,
    currency: str,
    company_name: str,
    ticker: str,
    cik: str,
    source_url: str,
) -> tuple[FinancialFact, ...]:
    """
    Select a directly reported standalone-quarter fact for a single filing.

    Tries catalog concepts in order and returns the first with a standalone
    quarter. Same-concept duplicates still raise AmbiguousFactError. A later
    concept is only a fallback when earlier ones have no quarterly candidate.
    Never derives values by subtraction.
    """
    concept_candidates = get_concept_candidates(metric)
    for taxonomy, concept in concept_candidates:
        concept_facts = [
            fact for fact in facts if fact.taxonomy == taxonomy and fact.concept == concept
        ]
        if not concept_facts:
            continue

        candidates = _filter_quarterly_candidates(
            concept_facts, filing, taxonomy, concept, currency
        )
        if not candidates:
            continue

        selected = _resolve_same_concept_candidates(candidates)
        return (
            _build_financial_fact(
                selected, metric, currency, company_name, ticker, cik, source_url
            ),
        )

    raise UnsupportedQuarterlyFactError(
        "No directly reported standalone-quarter fact exists for metric",
        details={
            "metric": metric.value,
            "filing_accession": filing.accession_number,
            "report_date": filing.report_date.isoformat(),
        },
    )


def select_quarterly_fact_with_filing_fallback(
    facts: list[FactRecord],
    filings: list[Filing],
    metric: Metric,
    currency: str,
    company_name: str,
    ticker: str,
    cik: str,
    source_url_for_filing: Callable[[Filing], str],
    *,
    report_date: date | None = None,
) -> tuple[FinancialFact, ...]:
    """
    Select quarterly facts using amendment-first filing fallback.

    Tries each candidate filing for the chosen report_date (newest when omitted)
    in order without mixing facts across accessions. UnsupportedQuarterlyFactError
    from a filing triggers fallback; AmbiguousFactError is never concealed by
    fallback. A missing named report_date is a typed filing failure, not the
    nearest available period.
    """
    try:
        candidate_filings = get_candidate_filings(filings, report_date=report_date)
    except FilingNotFoundError:
        raise

    last_unsupported: UnsupportedQuarterlyFactError | None = None
    for filing in candidate_filings:
        try:
            return select_quarterly_fact(
                facts,
                filing,
                metric,
                currency,
                company_name,
                ticker,
                cik,
                source_url_for_filing(filing),
            )
        except AmbiguousFactError:
            raise
        except UnsupportedQuarterlyFactError as exc:
            last_unsupported = exc

    if last_unsupported is not None:
        raise last_unsupported

    raise UnsupportedQuarterlyFactError(
        "No directly reported standalone-quarter fact exists for metric",
        details={"metric": metric.value},
    )
