"""Explain with numeral lock through run_turn."""

from types import SimpleNamespace

from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY, fixture_runtime
from financial_analyst_agent.turn import (
    MODEL_ANALYSIS_BANNER,
    EssayCompleter,
    Intent,
    RendererKind,
    Runtime,
    run_turn,
)

AI_HEALTHCARE_QUERY = "How can AI disrupt healthcare?"


class _ExplainCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        if query != AI_HEALTHCARE_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return SimpleNamespace(intent=Intent.EXPLAIN, topic=query)


class _NumberFreeEssay:
    def complete_essay(self, query: str) -> str:
        if query != AI_HEALTHCARE_QUERY:
            raise AssertionError(f"unexpected essay query: {query!r}")
        return FIXTURE_EXPLAIN_ESSAY


class _ExplodingFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        raise AssertionError("explain must not look up financials")


class _ExplodingRanking:
    def rank_companies(self, industry: str, limit: int) -> SimpleNamespace:
        raise AssertionError("explain must not rank companies")


def _explain_runtime(essay: EssayCompleter) -> Runtime:
    return Runtime(
        completer=_ExplainCompleter(),
        facts=_ExplodingFacts(),
        ranking=_ExplodingRanking(),
        essay=essay,
    )


class _InventedDollarEssay:
    def complete_essay(self, query: str) -> str:
        return "AI imaging will create a $29.8B market without citing a filing."


def test_run_turn_explain_returns_model_analysis_essay_without_retrieval() -> None:
    result = run_turn(AI_HEALTHCARE_QUERY, _explain_runtime(_NumberFreeEssay()))

    assert result.intent is Intent.EXPLAIN
    assert result.renderer is RendererKind.ESSAY
    assert MODEL_ANALYSIS_BANNER in result.banners
    assert result.essay == FIXTURE_EXPLAIN_ESSAY
    assert result.table_rows == []
    assert result.numeral_lock_extras == []
    tools = [trace.tool for trace in result.tool_traces]
    assert "search_news" not in tools
    assert "get_financials" not in tools
    assert "rank_companies" not in tools


def test_run_turn_explain_fails_numeral_lock_on_novel_dollars() -> None:
    result = run_turn(AI_HEALTHCARE_QUERY, _explain_runtime(_InventedDollarEssay()))

    assert result.intent is Intent.EXPLAIN
    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert MODEL_ANALYSIS_BANNER not in result.banners
    assert result.numeral_lock_extras
    assert any("29.8" in extra for extra in result.numeral_lock_extras)
    assert result.message is not None
    assert "29.8" in result.message


def test_fixture_runtime_explain_uses_injected_essay_completer() -> None:
    result = run_turn(AI_HEALTHCARE_QUERY, fixture_runtime())

    assert result.intent is Intent.EXPLAIN
    assert result.renderer is RendererKind.ESSAY
    assert MODEL_ANALYSIS_BANNER in result.banners
    assert result.essay is not None
    assert result.essay.strip()
    assert result.numeral_lock_extras == []
    tools = [trace.tool for trace in result.tool_traces]
    assert "search_news" not in tools

