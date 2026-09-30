"""Fiscal labels for filings, named periods, and the gross-profit fallback.

A filing's XBRL declares the fiscal year and period it covers (``fy`` and
``fp`` on every fact it reports), so "Q3 2024" means what the company itself
calls its third quarter of fiscal 2024, as companies and the press name
quarters (ADR 0007).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from financial_analyst_agent.domain.enums import FormType, Metric
from financial_analyst_agent.domain.errors import UnsupportedQuarterlyFactError
from financial_analyst_agent.domain.models import (
    Derivation,
    DerivationPart,
    Filing,
    FinancialFact,
)
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE

_PERIODIC_FORMS = frozenset(
    {FormType.FORM_10_Q, FormType.FORM_10_Q_A, FormType.FORM_10_K, FormType.FORM_10_K_A}
)
_ANNUAL_FORMS = frozenset({FormType.FORM_10_K, FormType.FORM_10_K_A})
_QUARTER_OF_PERIOD = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}
GROSS_PROFIT_LABEL = "Revenue minus cost of revenue"


@dataclass(frozen=True)
class FiscalLabel:
    """The fiscal year and period a filing declares (``fy``, ``fp``)."""

    fiscal_year: int | None
    fiscal_period: str | None


@dataclass(frozen=True)
class FiscalPeriod:
    """One quarter end with the fiscal year and quarter its filing declares."""

    end: date
    fiscal_year: int | None
    quarter: int | None
    form: str


def fiscal_labels(payload: dict[str, Any]) -> dict[str, FiscalLabel]:
    """Accession → declared fiscal year and period, from any fact the filing reports."""
    labels: dict[str, FiscalLabel] = {}
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return labels
    for concepts in facts.values():
        if not isinstance(concepts, dict):
            continue
        for concept in concepts.values():
            units = concept.get("units") if isinstance(concept, dict) else None
            if not isinstance(units, dict):
                continue
            for entries in units.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    accession = entry.get("accn")
                    if not isinstance(accession, str) or accession in labels:
                        continue
                    year = entry.get("fy")
                    period = entry.get("fp")
                    labels[accession] = FiscalLabel(
                        year if isinstance(year, int) else None,
                        period if isinstance(period, str) else None,
                    )
    return labels


def periods_from_filings(
    filings: list[Filing], labels: dict[str, FiscalLabel]
) -> tuple[FiscalPeriod, ...]:
    """Newest-first quarter ends, each labelled by its original filing."""
    by_end: dict[date, FiscalPeriod] = {}
    # The original filing names the period; an amendment repeats it.
    for filing in sorted(filings, key=lambda item: item.filed_date):
        if filing.form not in _PERIODIC_FORMS:
            continue
        if any(abs(end - filing.report_date) <= FISCAL_WEEK_TOLERANCE for end in by_end):
            continue
        label = labels.get(filing.accession_number, FiscalLabel(None, None))
        quarter = _QUARTER_OF_PERIOD.get(label.fiscal_period or "")
        if filing.form in _ANNUAL_FORMS:
            quarter = 4
        by_end[filing.report_date] = FiscalPeriod(
            end=filing.report_date,
            fiscal_year=label.fiscal_year,
            quarter=quarter,
            form=filing.form,
        )
    return _sequenced(tuple(sorted(by_end.values(), key=lambda period: period.end, reverse=True)))


def _sequenced(periods: tuple[FiscalPeriod, ...]) -> tuple[FiscalPeriod, ...]:
    """Newest-first periods, with quarters that repeat the year just closed renumbered.

    A filing's own ``fy`` is sometimes wrong: Oracle's 10-Q for the quarter ended
    August 31, 2026 (Q1 of fiscal 2027) declares 2026, the year its 10-K just
    closed, and NetApp's first two quarters of fiscal 2026 declare 2025. A Q1
    that follows a Q4 of the same fiscal year belongs to the next year, with
    the quarters after it that keep that label. When the Q4's own label is not
    confirmed by the 10-K a year before it, a later report keeping the year
    means the Q4 is the wrong one, and nothing is renumbered; so too when the
    next 10-K closes that same year. Only filed labels
    are compared, so one bad label never shifts the rest.
    """
    ordered = list(reversed(periods))
    repaired = list(ordered)
    for index in range(1, len(ordered)):
        closed, period = ordered[index - 1], ordered[index]
        if not (
            closed.quarter == 4
            and period.quarter == 1
            and period.fiscal_year is not None
            and period.fiscal_year == closed.fiscal_year
        ):
            continue
        year = period.fiscal_year
        earlier = [item for item in ordered[: index - 1] if item.quarter == 4]
        confirmed = not earlier or earlier[-1].fiscal_year == year - 1
        run = index
        while (
            run < len(ordered)
            and ordered[run].quarter in (1, 2, 3)
            and ordered[run].fiscal_year == year
        ):
            run += 1
        if not confirmed and run < len(ordered) and ordered[run].fiscal_year == year:
            continue
        if not confirmed and run - index > 1:
            continue
        following = next((item for item in ordered[run:] if item.quarter == 4), None)
        if following is not None and following.fiscal_year == year:
            # The next 10-K closes this year: the Q4 before was the mislabelled one
            # (Domino's 53-week year ending January 1, 2023 declares 2023).
            continue
        for fixed in range(index, run):
            repaired[fixed] = replace(ordered[fixed], fiscal_year=year + 1)
    return tuple(reversed(_labelled_forward(repaired)))


# A quarter's end is 12 to 14 weeks after the one before it.
_NEXT_QUARTER_DAYS = (80, 100)


def _labelled_forward(ordered: list[FiscalPeriod]) -> list[FiscalPeriod]:
    """Oldest-first periods, the newest unlabelled ones numbered from the one before.

    SEC's company facts can lag a filing by weeks: Coca-Cola's 10-Q for the
    quarter ended June 27, 2026 is listed but carries no fiscal year yet, so
    "Q2 2026" found nothing. The quarter after Q1 of 2026 is Q2 of 2026.
    """
    labelled = list(ordered)
    low, high = _NEXT_QUARTER_DAYS
    for index in range(1, len(labelled)):
        before, period = labelled[index - 1], labelled[index]
        if period.fiscal_year is not None or before.fiscal_year is None:
            continue
        if before.quarter is None or not low <= (period.end - before.end).days <= high:
            continue
        quarter = before.quarter % 4 + 1
        if (period.quarter or quarter) != quarter:
            continue
        year = before.fiscal_year + (1 if before.quarter == 4 else 0)
        labelled[index] = replace(period, fiscal_year=year, quarter=quarter)
    return labelled


def calendar_quarter(end: date) -> tuple[int, int]:
    """(year, quarter) holding the middle of the quarter that ends on ``end``."""
    middle = end - timedelta(days=45)
    return middle.year, (middle.month - 1) // 3 + 1


def dates_for(
    periods: tuple[FiscalPeriod, ...], year: int, quarter: int | None, *, calendar: bool
) -> tuple[date, ...]:
    """Newest-first quarter ends a named year (or one of its quarters) covers."""
    matched: list[date] = []
    for period in periods:
        if calendar:
            period_year, period_quarter = calendar_quarter(period.end)
        else:
            if period.fiscal_year is None or period.quarter is None:
                continue
            period_year, period_quarter = period.fiscal_year, period.quarter
        if period_year == year and (quarter is None or period_quarter == quarter):
            matched.append(period.end)
    return tuple(matched)


def gross_profit_from_components(revenue: FinancialFact, cost: FinancialFact) -> FinancialFact:
    """Gross profit as revenue minus cost of revenue, for filers that tag no gross profit."""

    def part(fact: FinancialFact) -> DerivationPart:
        return DerivationPart(
            value=fact.value,
            start_date=fact.start_date,
            end_date=fact.end_date,
            form=fact.form,
            accession_number=fact.accession_number,
            taxonomy=fact.taxonomy,
            concept=fact.concept,
            filed_date=fact.filed_date,
            source_url=fact.source_url,
            derivation=fact.derivation,
            metric=fact.metric.value,
        )

    return revenue.model_copy(
        update={
            "metric": Metric.GROSS_PROFIT,
            "value": revenue.value - cost.value,
            "concept": f"{revenue.concept} − {cost.concept}",
            "directly_reported": False,
            "derivation": Derivation(
                method="revenue_minus_cost_of_revenue",
                label=GROSS_PROFIT_LABEL,
                parts=[part(revenue), part(cost)],
            ),
        }
    )


REVENUE_FROM_COMPONENTS_LABEL = (
    "Gross profit plus cost of revenue, because the filing's own revenue figure "
    "is smaller than either and so mis-scaled"
)


def revenue_from_components(
    filed: FinancialFact, gross: FinancialFact, cost: FinancialFact
) -> FinancialFact:
    """Revenue as gross profit plus cost of revenue, when the filed revenue is mis-scaled."""
    return filed.model_copy(
        update={
            "value": gross.value + cost.value,
            "concept": f"{gross.concept} + {cost.concept}",
            "accession_number": gross.accession_number,
            "form": gross.form,
            "source_url": gross.source_url,
            "directly_reported": False,
            "derivation": Derivation(
                method="sum",
                label=REVENUE_FROM_COMPONENTS_LABEL,
                parts=[
                    _derivation_part(gross).model_copy(update={"metric": gross.metric.value}),
                    _derivation_part(cost).model_copy(update={"metric": cost.metric.value}),
                ],
            ),
        }
    )


DEPRECIATION_AMORTIZATION_LABEL = "Depreciation plus amortization of intangible assets"


def sum_of_components(metric: Metric, facts: list[FinancialFact]) -> FinancialFact:
    """One amount as the sum of reported parts that cover the same period."""
    first = facts[0]
    period = (first.start_date, first.end_date)
    if any((fact.start_date, fact.end_date) != period for fact in facts):
        raise UnsupportedQuarterlyFactError(
            "The parts of the amount cover different periods",
            details={"metric": metric.value},
        )
    return first.model_copy(
        update={
            "metric": metric,
            "value": sum((fact.value for fact in facts), start=Decimal(0)),
            "concept": " + ".join(fact.concept for fact in facts),
            "directly_reported": False,
            "derivation": Derivation(
                method="sum",
                label=DEPRECIATION_AMORTIZATION_LABEL,
                parts=[_derivation_part(fact) for fact in facts],
            ),
        }
    )


def _derivation_part(fact: FinancialFact) -> DerivationPart:
    return DerivationPart(
        value=fact.value,
        start_date=fact.start_date,
        end_date=fact.end_date,
        form=fact.form,
        accession_number=fact.accession_number,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        filed_date=fact.filed_date,
        source_url=fact.source_url,
        derivation=fact.derivation,
    )
