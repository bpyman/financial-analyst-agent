import pytest

from financial_analyst_agent.domain.errors import UnknownMetricError
from financial_analyst_agent.services.metric_catalog import parse_metric, resolve_metric_phrase
from financial_analyst_agent.turn import ALLOWED_METRICS


def test_profit_is_ambiguous_among_profit_concepts() -> None:
    resolved = resolve_metric_phrase("What was Google's profit?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("gross_profit", "operating_income", "net_income")


def test_profit_margin_is_ambiguous_among_margins() -> None:
    resolved = resolve_metric_phrase("What was Google's profit margin?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("gross_margin", "operating_margin", "net_margin")


def test_gross_profit_is_unique_catalog_name() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's gross profit based on their latest quarterly report?"
    )
    assert resolved.kind == "unique"
    assert resolved.metric == "gross_profit"


def test_net_income_is_unique_catalog_name() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's net income based on their latest quarterly report?"
    )
    assert resolved.kind == "unique"
    assert resolved.metric == "net_income"


def test_net_margin_is_unique_catalog_name() -> None:
    resolved = resolve_metric_phrase("Shopify net margin")
    assert resolved.kind == "unique"
    assert resolved.metric == "net_margin"


def test_revenue_is_unique_catalog_name() -> None:
    resolved = resolve_metric_phrase("What was Google's revenue?")
    assert resolved.kind == "unique"
    assert resolved.metric == "revenue"


def test_income_is_ambiguous_not_net_income() -> None:
    resolved = resolve_metric_phrase("What was Google's income?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("net_income", "operating_income")


def test_reported_income_is_ambiguous() -> None:
    resolved = resolve_metric_phrase(
        "What are the top 10 healthcare companies and the reported income for each?"
    )
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("net_income", "operating_income")


def test_operating_profit_is_unique_operating_income() -> None:
    resolved = resolve_metric_phrase("What was Google's operating profit?")
    assert resolved.kind == "unique"
    assert resolved.metric == "operating_income"


def test_operating_alone_is_unknown() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's operating based on their latest quarterly report?"
    )
    assert resolved.kind == "unknown"


def test_earnings_alias_is_unique_net_income() -> None:
    resolved = resolve_metric_phrase("What was Google's earnings?")
    assert resolved.kind == "unique"
    assert resolved.metric == "net_income"


def test_sales_alias_is_unique_revenue() -> None:
    resolved = resolve_metric_phrase("What was Google's sales?")
    assert resolved.kind == "unique"
    assert resolved.metric == "revenue"


def test_cost_of_sales_is_unique_cost_of_revenue() -> None:
    resolved = resolve_metric_phrase("What was Google's cost of sales?")
    assert resolved.kind == "unique"
    assert resolved.metric == "cost_of_revenue"


def test_ebit_alias_is_unique_operating_income() -> None:
    resolved = resolve_metric_phrase("What was Google's EBIT?")
    assert resolved.kind == "unique"
    assert resolved.metric == "operating_income"


def test_ebitda_is_unknown() -> None:
    resolved = resolve_metric_phrase("What was Google's EBITDA?")
    assert resolved.kind == "unknown"


def test_two_unique_catalog_names_are_ambiguous() -> None:
    resolved = resolve_metric_phrase("Compare Google revenue and net income")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("revenue", "net_income")


def test_roe_is_unknown() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's ROE based on their latest quarterly report?"
    )
    assert resolved.kind == "unknown"


def test_costs_is_unknown() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's costs based on their latest quarterly report?"
    )
    assert resolved.kind == "unknown"


def test_operating_margins_plural_is_unique_operating_margin() -> None:
    resolved = resolve_metric_phrase("Compare Microsoft and Google operating margins")
    assert resolved.kind == "unique"
    assert resolved.metric == "operating_margin"


def test_research_and_development_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's research and development?")
    assert resolved.kind == "unique"
    assert resolved.metric == "research_and_development"


def test_rd_abbreviation_is_unique_research_and_development() -> None:
    resolved = resolve_metric_phrase("What was Google's R&D?")
    assert resolved.kind == "unique"
    assert resolved.metric == "research_and_development"


def test_rd_spend_is_unique_research_and_development() -> None:
    resolved = resolve_metric_phrase("Top 10 tech companies R&D spend")
    assert resolved.kind == "unique"
    assert resolved.metric == "research_and_development"


def test_sga_abbreviation_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's SG&A?")
    assert resolved.kind == "unique"
    assert resolved.metric == "selling_general_and_administrative"


def test_interest_expense_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's interest expense?")
    assert resolved.kind == "unique"
    assert resolved.metric == "interest_expense"


def test_interest_alone_is_ambiguous() -> None:
    resolved = resolve_metric_phrase("What was Google's interest?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("interest_expense", "interest_coverage")


def test_income_tax_is_unique_tax_expense() -> None:
    resolved = resolve_metric_phrase("What was Google's income tax?")
    assert resolved.kind == "unique"
    assert resolved.metric == "income_tax_expense"


def test_tax_alone_is_ambiguous() -> None:
    resolved = resolve_metric_phrase("What was Google's tax?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("income_tax_expense", "effective_tax_rate")


def test_pretax_income_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's pretax income?")
    assert resolved.kind == "unique"
    assert resolved.metric == "pretax_income"


def test_rd_to_sales_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's R&D to sales?")
    assert resolved.kind == "unique"
    assert resolved.metric == "rd_to_sales"


def test_effective_tax_rate_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's effective tax rate?")
    assert resolved.kind == "unique"
    assert resolved.metric == "effective_tax_rate"


def test_interest_coverage_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's interest coverage?")
    assert resolved.kind == "unique"
    assert resolved.metric == "interest_coverage"


def test_market_cap_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's market cap?")
    assert resolved.kind == "unique"
    assert resolved.metric == "market_cap"


def test_market_alone_is_unknown() -> None:
    resolved = resolve_metric_phrase("What was Google's market?")
    assert resolved.kind == "unknown"


@pytest.mark.parametrize("metric", ALLOWED_METRICS)
def test_catalog_slug_is_unique(metric: str) -> None:
    resolved = resolve_metric_phrase(f"What was Google's {metric}?")
    assert resolved.kind == "unique"
    assert resolved.metric == metric


def test_parse_metric_unknown_raises_unknown_metric_error() -> None:
    with pytest.raises(UnknownMetricError):
        parse_metric("roe")
