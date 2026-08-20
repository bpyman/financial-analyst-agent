"""News search adapters: recorded hits offline, Tavily Search live."""

from typing import Any

import httpx

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.turn import (
    SEARCH_NEWS_MAX_RESULTS,
    SEARCH_NEWS_TIME_RANGE,
    SEARCH_NEWS_TOPIC,
    NewsHit,
)

FIXTURE_NEWS_HITS: tuple[NewsHit, ...] = (
    NewsHit(
        title="NVIDIA flags CoWoS supply constraints",
        url="https://example.test/nvidia-supply-chain",
        snippet="Lead times remain extended after $12.3B of data-center demand.",
        score=0.91,
        published="2026-08-10",
    ),
)
FIXTURE_NEWS_QUERY = "What is going on with NVIDIA supply chain?"


class FixtureNewsSearch:
    """Recorded Tavily-shaped hits so news_and_explain stays offline."""

    def search_news(self, query: str) -> list[NewsHit]:
        if query.strip().casefold() != FIXTURE_NEWS_QUERY.casefold():
            return []
        return list(FIXTURE_NEWS_HITS)


def _parse_tavily_score(value: Any) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def hits_from_tavily_payload(payload: dict[str, Any]) -> list[NewsHit]:
    """Map Tavily Search JSON to usable hits. Extract/map/crawl are not used."""
    hits: list[NewsHit] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        published = item.get("published_date") or item.get("published")
        published_text = str(published).strip() if published else None
        hits.append(
            NewsHit(
                title=title,
                url=url,
                snippet=str(item.get("content") or item.get("snippet") or ""),
                score=_parse_tavily_score(item.get("score")),
                published=published_text or None,
            )
        )
        if len(hits) >= SEARCH_NEWS_MAX_RESULTS:
            break
    return hits


class TavilyNewsSearch:
    """Tavily Search with topic=news. Not ticker-only FMP news or DuckDuckGo."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._base_url = settings.tavily_base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def search_news(self, query: str) -> list[NewsHit]:
        api_key = self._settings.require_tavily_api_key()
        try:
            response = self._http().post(
                f"{self._base_url}/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "topic": SEARCH_NEWS_TOPIC,
                    "max_results": SEARCH_NEWS_MAX_RESULTS,
                    "time_range": SEARCH_NEWS_TIME_RANGE,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("Tavily search failed", details={"query": query}) from exc
        if not isinstance(payload, dict):
            raise ProviderError("Tavily search returned a non-object payload")
        return hits_from_tavily_payload(payload)
