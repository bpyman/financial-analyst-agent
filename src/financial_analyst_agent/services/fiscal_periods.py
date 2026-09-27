"""Fiscal labels for filings, named periods, and the gross-profit fallback.

A filing's XBRL declares the fiscal year and period it covers (``fy`` and
``fp`` on every fact it reports), so "Q3 2024" means what the company itself
calls its third quarter of fiscal 2024, as companies and the press name
quarters (ADR 0007).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from financial_analyst_agent.domain.enums import FormType, Metric
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
    return tuple(sorted(by_end.values(), key=lambda period: period.end, reverse=True))


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
