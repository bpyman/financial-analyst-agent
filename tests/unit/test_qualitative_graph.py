"""The qualitative workflows the analysis graph's essay nodes call.

Asserts the explain and current-events workflows return the same TurnResult
shape as before. Does not assert node names, channels, or LangGraph internals.
"""

from __future__ import annotations

from types import SimpleNamespace

from financial_analyst_agent.news import FIXTURE_NEWS_QUERY
from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY


class _SilentCompleter:
    def complete(self, query: str, current_spec: object = None) -> SimpleNamespace:
        raise AssertionError("an essay workflow must not re-plan")


class _NumberFreeEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return FIXTURE_EXPLAIN_ESSAY


class _GroundedNewsEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        if "$12.3B" not in tool_json:
            raise AssertionError("essay must receive news hit JSON")
        return (
            "Coverage of NVIDIA's supply chain cited $12.3B of data-center demand "
            "and CoWoS constraints."
        )


class _ExplodingEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        raise AssertionError("empty news hits must not fall back to a memory essay")


class _FixtureNews:
    def search_news(self, query: str) -> list:
        from financial_analyst_agent.contracts import NewsHit

        return [
            NewsHit(
                title="NVIDIA flags CoWoS supply constraints",
                url="https://example.test/nvidia-supply-chain",
                snippet="Lead times remain extended after $12.3B of data-center demand.",
                score=0.91,
                published="2026-08-10",
            )
        ]


class _EmptyNews:
    def search_news(self, query: str) -> list:
        return []


def _runtime(*, essay: object | None = None, news: object | None = None) -> object:
    from financial_analyst_agent.contracts import Runtime

    return Runtime(
        completer=_SilentCompleter(),
        facts=SimpleNamespace(),  # type: ignore[arg-type]
        essay=essay,  # type: ignore[arg-type]
        news=news,  # type: ignore[arg-type]
    )


def test_explain_answer_returns_model_analysis_essay() -> None:
    from financial_analyst_agent.contracts import (
        MODEL_ANALYSIS_BANNER,
        Intent,
        RendererKind,
        TurnResult,
    )
    from financial_analyst_agent.turn import explain_answer

    result = explain_answer(
        "How can AI disrupt healthcare?",
        _runtime(essay=_NumberFreeEssay()),  # type: ignore[arg-type]
    )

    assert type(result).__name__ == TurnResult.__name__
    assert result.intent == Intent.EXPLAIN
    assert result.renderer == RendererKind.ESSAY
    assert MODEL_ANALYSIS_BANNER in result.banners
    assert result.essay == FIXTURE_EXPLAIN_ESSAY
    assert result.tool_traces[0].tool == "explain_topic"


def test_current_events_answer_returns_cited_essay() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.turn import current_events_answer

    result = current_events_answer(
        FIXTURE_NEWS_QUERY,
        _runtime(essay=_GroundedNewsEssay(), news=_FixtureNews()),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.NEWS_AND_EXPLAIN
    assert result.renderer == RendererKind.ESSAY
    assert result.citations
    assert result.tool_traces[0].tool == "search_news"


def test_current_events_answer_refuses_empty_hits_without_essay() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.turn import current_events_answer

    result = current_events_answer(
        FIXTURE_NEWS_QUERY,
        _runtime(essay=_ExplodingEssay(), news=_EmptyNews()),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.NEWS_AND_EXPLAIN
    assert result.renderer == RendererKind.REFUSE
    assert result.essay is None
