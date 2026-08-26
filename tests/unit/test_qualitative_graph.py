"""Qualitative workflows run through the parent graph (migration step 2).

Asserts the public graph entry returns the same TurnResult shape as today's
explain and news-and-explain paths. Does not assert node names, channels, or
LangGraph internals.
"""

from __future__ import annotations

from types import SimpleNamespace

from financial_analyst_agent.news import FIXTURE_NEWS_QUERY
from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY


class _SilentCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        raise AssertionError("workflow graph entry must not re-plan")


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


def test_run_workflow_turn_explain_returns_model_analysis_essay() -> None:
    from financial_analyst_agent.contracts import (
        MODEL_ANALYSIS_BANNER,
        Intent,
        RendererKind,
        TurnResult,
    )
    from financial_analyst_agent.graph import run_workflow_turn

    plan = SimpleNamespace(intent=Intent.EXPLAIN, topic="How can AI disrupt healthcare?")
    result = run_workflow_turn(
        plan,
        _runtime(essay=_NumberFreeEssay()),  # type: ignore[arg-type]
        query="How can AI disrupt healthcare?",
    )

    assert type(result).__name__ == TurnResult.__name__
    assert result.intent == Intent.EXPLAIN
    assert result.renderer == RendererKind.ESSAY
    assert MODEL_ANALYSIS_BANNER in result.banners
    assert result.essay == FIXTURE_EXPLAIN_ESSAY
    assert result.tool_traces[0].tool == "explain_topic"


def test_run_workflow_turn_news_returns_cited_essay() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.graph import run_workflow_turn

    plan = SimpleNamespace(intent=Intent.NEWS_AND_EXPLAIN, query=FIXTURE_NEWS_QUERY)
    result = run_workflow_turn(
        plan,
        _runtime(essay=_GroundedNewsEssay(), news=_FixtureNews()),  # type: ignore[arg-type]
        query=FIXTURE_NEWS_QUERY,
    )

    assert result.intent == Intent.NEWS_AND_EXPLAIN
    assert result.renderer == RendererKind.ESSAY
    assert result.citations
    assert result.tool_traces[0].tool == "search_news"


def test_run_workflow_turn_news_refuses_empty_hits_without_essay() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.graph import run_workflow_turn

    plan = SimpleNamespace(intent=Intent.NEWS_AND_EXPLAIN, query=FIXTURE_NEWS_QUERY)
    result = run_workflow_turn(
        plan,
        _runtime(essay=_ExplodingEssay(), news=_EmptyNews()),  # type: ignore[arg-type]
        query=FIXTURE_NEWS_QUERY,
    )

    assert result.intent == Intent.NEWS_AND_EXPLAIN
    assert result.renderer == RendererKind.REFUSE
    assert result.essay is None
