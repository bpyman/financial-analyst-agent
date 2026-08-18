"""Optional live OpenAI planner. Skipped in the default suite."""

import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.planner import OpenAIStructuredCompleter
from financial_analyst_agent.turn import Intent
from test_run_turn_compare import MSFT_GOOG_OPERATING_MARGINS_QUERY
from test_run_turn_explain import AI_HEALTHCARE_QUERY
from test_run_turn_lookup import GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY
from test_run_turn_news import NVIDIA_SUPPLY_QUERY
from test_run_turn_rank_and_lookup import HEALTHCARE_INCOME_QUERY


@pytest.mark.network
@pytest.mark.parametrize(
    ("query", "intent"),
    [
        (GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, Intent.LOOKUP),
        (HEALTHCARE_INCOME_QUERY, Intent.RANK_AND_LOOKUP),
        (MSFT_GOOG_OPERATING_MARGINS_QUERY, Intent.COMPARE),
        (AI_HEALTHCARE_QUERY, Intent.EXPLAIN),
        (NVIDIA_SUPPLY_QUERY, Intent.NEWS_AND_EXPLAIN),
    ],
)
def test_openai_planner_maps_demo_prompts_to_closed_intents(
    query: str, intent: Intent
) -> None:
    settings = Settings()
    if not settings.openai_api_key.strip() or not settings.openai_model.strip():
        pytest.skip("OPENAI_API_KEY and OPENAI_MODEL required for live planner")

    plan = OpenAIStructuredCompleter.from_settings(settings).complete(query)
    assert plan.intent is intent
