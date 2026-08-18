"""Closed metric enum to XBRL concept candidate mapping."""

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import AmbiguousMetricError

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
        ("us-gaap", "CostsAndExpenses"),
    ],
    Metric.OPERATING_INCOME: [
        ("us-gaap", "OperatingIncomeLoss"),
    ],
}


def get_concept_candidates(metric: Metric) -> list[tuple[str, str]]:
    """Return ordered (taxonomy, concept) candidates for a validated metric."""
    return METRIC_CONCEPTS[metric]


def parse_metric(term: str) -> Metric:
    """Parse a user metric term into a closed Metric enum value."""
    normalized = term.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return Metric(normalized)
    except ValueError:
        raise AmbiguousMetricError(
            f"Unknown metric '{term}'",
            details={"term": term, "allowed": [metric.value for metric in Metric]},
        ) from None
