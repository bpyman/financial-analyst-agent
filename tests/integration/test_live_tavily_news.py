"""Optional live Tavily news_and_explain. Skipped in the default suite."""

import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.facts import RecordedSECDataSource
from financial_analyst_agent.news import TavilyNewsSearch
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import DemoCompleter, FixtureEssayCompleter
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.turn import Intent, RendererKind, Runtime, RuntimeKind, run_turn
from test_run_turn_news import NVIDIA_SUPPLY_QUERY


@pytest.mark.network
def test_run_turn_live_tavily_news_and_explain() -> None:
    settings = Settings()
    if not settings.tavily_api_key.strip():
        pytest.skip("TAVILY_API_KEY required for live Tavily")

    result = run_turn(
        NVIDIA_SUPPLY_QUERY,
        Runtime(
            completer=DemoCompleter(),
            facts=SecFactLookup(client=RecordedSECDataSource()),
            ranking=SnapshotRanking.from_path(),
            news=TavilyNewsSearch(settings),
            essay=FixtureEssayCompleter(),
            kind=RuntimeKind.LIVE,
        ),
    )

    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.tool_traces[0].tool == "search_news"
    assert result.tool_traces[0].args["query"] == NVIDIA_SUPPLY_QUERY
    assert result.tool_traces[0].args["topic"] == "news"
    assert result.tool_traces[0].args["max_results"] == 5
    if result.renderer is RendererKind.ESSAY:
        assert result.citations
        assert all(hit.title and hit.url for hit in result.citations)
        assert result.numeral_lock_extras == []
        return
    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
