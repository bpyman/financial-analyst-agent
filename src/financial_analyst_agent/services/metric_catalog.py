"""Closed metric enum to XBRL concept candidate mapping."""

import re
from dataclasses import dataclass
from typing import Literal

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import UnknownMetricError

METRIC_CONCEPTS: dict[Metric, list[tuple[str, str]]] = {
    Metric.NET_INCOME: [
        ("us-gaap", "NetIncomeLoss"),
        ("us-gaap", "ProfitLoss"),
    ],
    Metric.REVENUE: [
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"),
    ],
    Metric.COST_OF_REVENUE: [
        ("us-gaap", "CostOfRevenue"),
        ("us-gaap", "CostOfGoodsAndServicesSold"),
    ],
    Metric.GROSS_PROFIT: [
        ("us-gaap", "GrossProfit"),
    ],
    Metric.OPERATING_EXPENSES: [
        ("us-gaap", "OperatingExpenses"),
    ],
    Metric.OPERATING_INCOME: [
        ("us-gaap", "OperatingIncomeLoss"),
    ],
    Metric.RESEARCH_AND_DEVELOPMENT: [
        ("us-gaap", "ResearchAndDevelopmentExpense"),
    ],
    Metric.SELLING_GENERAL_AND_ADMINISTRATIVE: [
        ("us-gaap", "SellingGeneralAndAdministrativeExpense"),
    ],
    Metric.INTEREST_EXPENSE: [
        ("us-gaap", "InterestExpense"),
        ("us-gaap", "InterestExpenseDebt"),
    ],
    Metric.INCOME_TAX_EXPENSE: [
        ("us-gaap", "IncomeTaxExpenseBenefit"),
        ("us-gaap", "IncomeTaxExpenseBenefitContinuingOperations"),
    ],
    Metric.PRETAX_INCOME: [
        (
            "us-gaap",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
            "ExtraordinaryItemsNoncontrollingInterest",
        ),
        ("us-gaap", "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"),
        ("us-gaap", "PretaxIncomeLoss"),
    ],
}

MetricPhraseKind = Literal["unique", "ambiguous", "unknown"]


@dataclass(frozen=True)
class MetricPhraseResolution:
    kind: MetricPhraseKind
    metric: str | None = None
    metrics: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()


def get_concept_candidates(metric: Metric) -> list[tuple[str, str]]:
    """Return ordered (taxonomy, concept) candidates for a validated metric."""
    return METRIC_CONCEPTS[metric]


def parse_metric(term: str) -> Metric:
    """Parse a user metric term into a closed Metric enum value."""
    normalized = term.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return Metric(normalized)
    except ValueError:
        raise UnknownMetricError(
            f"Unknown metric '{term}'",
            details={"term": term, "allowed": [metric.value for metric in Metric]},
        ) from None


_UNIQUE_PHRASES: tuple[tuple[str, str], ...] = (
    ("cost of goods and services", "cost_of_revenue"),
    ("cost of goods sold", "cost_of_revenue"),
    ("cost of sales", "cost_of_revenue"),
    ("cost of revenue", "cost_of_revenue"),
    ("cost_of_revenue", "cost_of_revenue"),
    ("cogs", "cost_of_revenue"),
    ("selling general and administrative", "selling_general_and_administrative"),
    ("selling, general and administrative", "selling_general_and_administrative"),
    ("selling_general_and_administrative", "selling_general_and_administrative"),
    ("sg&a ratio", "sga_ratio"),
    ("sga ratio", "sga_ratio"),
    ("sga_ratio", "sga_ratio"),
    ("sg&a", "selling_general_and_administrative"),
    ("sga", "selling_general_and_administrative"),
    ("research and development to sales", "rd_to_sales"),
    ("research and development", "research_and_development"),
    ("research_and_development", "research_and_development"),
    ("r&d to sales", "rd_to_sales"),
    ("rd to sales", "rd_to_sales"),
    ("r&d spend", "research_and_development"),
    ("r&d intensity", "rd_to_sales"),
    ("rd_to_sales", "rd_to_sales"),
    ("r&d", "research_and_development"),
    ("operating expenses", "operating_expenses"),
    ("operating_expenses", "operating_expenses"),
    ("operating costs", "operating_expenses"),
    ("opex", "operating_expenses"),
    ("operating profit margin", "operating_margin"),
    ("operating income", "operating_income"),
    ("operating_income", "operating_income"),
    ("operating profit", "operating_income"),
    ("operating earnings", "operating_income"),
    ("ebit", "operating_income"),
    ("operating margin", "operating_margin"),
    ("operating_margin", "operating_margin"),
    ("operating margins", "operating_margin"),
    ("ebit margin", "operating_margin"),
    ("gross profit margin", "gross_margin"),
    ("gross profit", "gross_profit"),
    ("gross_profit", "gross_profit"),
    ("gross margin", "gross_margin"),
    ("gross_margin", "gross_margin"),
    ("gross margins", "gross_margin"),
    ("effective tax rate", "effective_tax_rate"),
    ("effective_tax_rate", "effective_tax_rate"),
    ("tax rate", "effective_tax_rate"),
    ("income tax expense", "income_tax_expense"),
    ("income_tax_expense", "income_tax_expense"),
    ("tax expense", "income_tax_expense"),
    ("income tax", "income_tax_expense"),
    ("interest coverage ratio", "interest_coverage"),
    ("interest coverage", "interest_coverage"),
    ("interest_coverage", "interest_coverage"),
    ("interest expense", "interest_expense"),
    ("interest_expense", "interest_expense"),
    ("interest costs", "interest_expense"),
    ("income before tax", "pretax_income"),
    ("pre-tax income", "pretax_income"),
    ("pretax income", "pretax_income"),
    ("pretax_income", "pretax_income"),
    ("net profit margin", "net_margin"),
    ("net income", "net_income"),
    ("net_income", "net_income"),
    ("net profit", "net_income"),
    ("net earnings", "net_income"),
    ("earnings", "net_income"),
    ("bottom line", "net_income"),
    ("net margin", "net_margin"),
    ("net_margin", "net_margin"),
    ("net margins", "net_margin"),
    ("net sales", "revenue"),
    ("sales", "revenue"),
    ("revenue", "revenue"),
    ("market capitalization", "market_cap"),
    ("market cap", "market_cap"),
    ("market_cap", "market_cap"),
    ("mkt cap", "market_cap"),
)

_AMBIGUOUS_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("profit margin", ("gross_margin", "operating_margin", "net_margin")),
    ("profit", ("gross_profit", "operating_income", "net_income")),
    ("income", ("net_income", "operating_income")),
    ("margin", ("gross_margin", "operating_margin", "net_margin")),
    ("gross", ("gross_profit", "gross_margin")),
    ("net", ("net_income", "net_margin")),
    ("interest", ("interest_expense", "interest_coverage")),
    ("tax", ("income_tax_expense", "effective_tax_rate")),
)


def _phrase_spans(query: str, phrase: str) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end()) for match in re.finditer(rf"\b{re.escape(phrase)}\b", query)
    ]


def _nonoverlapping_unique_matches(query: str) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for phrase, metric in _UNIQUE_PHRASES:
        for start, end in _phrase_spans(query, phrase):
            found.append((start, end, metric))
    found.sort(key=lambda item: (item[0] - item[1], item[0]))
    accepted: list[tuple[int, int, str]] = []
    for start, end, metric in found:
        if any(
            not (end <= other_start or start >= other_end) for other_start, other_end, _ in accepted
        ):
            continue
        accepted.append((start, end, metric))
    accepted.sort(key=lambda item: item[0])
    return accepted


def _spans_overlap(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(
        not (end <= other_start or start >= other_end) for other_start, other_end in occupied
    )


def _nonoverlapping_ambiguous_matches(
    query: str, occupied: list[tuple[int, int]]
) -> list[tuple[int, int, tuple[str, ...]]]:
    found: list[tuple[int, int, tuple[str, ...]]] = []
    for phrase, candidates in _AMBIGUOUS_PHRASES:
        for start, end in _phrase_spans(query, phrase):
            if _spans_overlap(start, end, occupied):
                continue
            found.append((start, end, candidates))
    found.sort(key=lambda item: (item[0] - item[1], item[0]))
    accepted: list[tuple[int, int, tuple[str, ...]]] = []
    accepted_spans: list[tuple[int, int]] = []
    for start, end, candidates in found:
        if _spans_overlap(start, end, accepted_spans):
            continue
        accepted.append((start, end, candidates))
        accepted_spans.append((start, end))
    accepted.sort(key=lambda item: item[0])
    return accepted


def resolve_metric_phrases(query: str) -> tuple[MetricPhraseResolution, ...]:
    """Classify each metric phrase in the user question, left to right."""
    normalized = query.casefold()
    unique_matches = _nonoverlapping_unique_matches(normalized)
    occupied = [(start, end) for start, end, _metric in unique_matches]
    ambiguous_matches = _nonoverlapping_ambiguous_matches(normalized, occupied)

    ordered: list[tuple[int, MetricPhraseResolution]] = [
        (start, MetricPhraseResolution(kind="unique", metric=metric, metrics=(metric,)))
        for start, _end, metric in unique_matches
    ]
    ordered.extend(
        (start, MetricPhraseResolution(kind="ambiguous", candidates=candidates))
        for start, _end, candidates in ambiguous_matches
    )
    ordered.sort(key=lambda item: item[0])
    return tuple(resolution for _start, resolution in ordered)


def resolve_metric_phrase(query: str) -> MetricPhraseResolution:
    """Classify metric phrases for the one-shot turn seam."""
    phrases = resolve_metric_phrases(query)
    if not phrases:
        return MetricPhraseResolution(kind="unknown")
    for phrase in phrases:
        if phrase.kind == "ambiguous":
            return phrase
    uniques = [phrase for phrase in phrases if phrase.kind == "unique"]
    if len(uniques) == 1:
        return uniques[0]
    if len(uniques) > 1:
        metrics = tuple(phrase.metric for phrase in uniques if phrase.metric is not None)
        return MetricPhraseResolution(kind="unique", metrics=metrics)
    return MetricPhraseResolution(kind="unknown")
