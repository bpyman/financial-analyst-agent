"""Tavily Search mapping. Extract/map/crawl are not used."""

import httpx
import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.news import TavilyNewsSearch, hits_from_tavily_payload
from financial_analyst_agent.turn import SEARCH_NEWS_MAX_RESULTS


def test_hits_from_tavily_payload_keeps_title_url_and_drops_unusable() -> None:
    hits = hits_from_tavily_payload(
        {
            "results": [
                {
                    "title": "NVIDIA supply chain",
                    "url": "https://example.test/nvda",
                    "content": "Lead times after $12.3B of demand.",
                    "score": 0.9,
                    "published_date": "2026-08-10",
                },
                {"title": "", "url": "https://example.test/missing-title"},
                {"title": "No URL", "url": ""},
                {"title": "Extract-only", "raw_content": "should not be a hit"},
            ]
        }
    )

    assert len(hits) == 1
    assert hits[0].title == "NVIDIA supply chain"
    assert hits[0].url == "https://example.test/nvda"
    assert "$12.3B" in hits[0].snippet
    assert hits[0].published == "2026-08-10"
    assert hits[0].score == 0.9


def test_hits_from_tavily_payload_caps_at_max_results() -> None:
    payload = {
        "results": [
            {"title": f"Hit {index}", "url": f"https://example.test/{index}"}
            for index in range(SEARCH_NEWS_MAX_RESULTS + 3)
        ]
    }
    hits = hits_from_tavily_payload(payload)
    assert len(hits) == SEARCH_NEWS_MAX_RESULTS


def test_tavily_news_wraps_invalid_json_as_provider_failure() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"not-json", request=request)
        )
    )
    search = TavilyNewsSearch(Settings(tavily_api_key="test-key"), client=client)

    with pytest.raises(ProviderError) as exc_info:
        search.search_news("NVIDIA supply chain")

    assert exc_info.value.details == {"query": "NVIDIA supply chain"}
