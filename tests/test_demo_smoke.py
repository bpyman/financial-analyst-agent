"""Smoke the fixture-first audience window and first guided story."""

from financial_analyst_agent.app import GUIDED_STORIES
from financial_analyst_agent.runtime import fixture_runtime
from financial_analyst_agent.turn import RendererKind, run_turn


def test_first_guided_story_returns_a_table() -> None:
    _, question = GUIDED_STORIES[0]
    result = run_turn(question, fixture_runtime())
    assert result.renderer is RendererKind.TABLE
    assert result.table_rows
    assert result.table_rows[0].value is not None
