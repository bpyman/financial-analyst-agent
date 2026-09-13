"""Smoke the fixture-first audience window and first guided story."""

from datetime import date
import os
import tomllib
from pathlib import Path

import pytest
from streamlit.runtime.secrets import Secrets

from financial_analyst_agent.app import GUIDED_STORIES
from financial_analyst_agent.config import AppMode, Settings
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.runtime import (
    FIXTURE_FILING_NEWER,
    FIXTURE_FILING_OLDER,
    DemoCompleter,
    fixture_runtime,
)
from financial_analyst_agent.thread_store import EphemeralThreadStore
from financial_analyst_agent.turn import Intent, RendererKind, run_turn


def test_first_guided_story_returns_a_table() -> None:
    _, question = GUIDED_STORIES[0]
    result = run_turn(question, fixture_runtime())
    assert result.renderer is RendererKind.TABLE
    assert result.table_rows
    assert result.table_rows[0].value is not None


def test_fixture_apple_last_four_quarters_revenue_has_values() -> None:
    result = run_turn(
        "What was Apple's quarterly revenue over the last four quarters?",
        fixture_runtime(),
    )
    rows = [row for row in result.table_rows if row.comparison is None]
    assert result.renderer is RendererKind.TABLE
    assert [row.ticker for row in rows] == ["AAPL"] * 4
    assert all(row.value is not None for row in rows)


def test_add_apple_after_microsoft_four_quarters_returns_apple_revenue() -> None:
    store = EphemeralThreadStore()
    runtime = fixture_runtime()
    _, question = GUIDED_STORIES[1]
    run_conversation_turn("demo", question, runtime, store=store)
    follow = run_conversation_turn("demo", "add Apple", runtime, store=store)
    valued = {
        row.end_date: row.value
        for row in follow.result.table_rows
        if row.ticker == "AAPL" and row.value is not None and row.comparison is None
    }
    assert valued[date(2026, 3, 31)] == 111_184_000_000
    assert valued[date(2024, 12, 31)] == 124_300_000_000
    assert valued[date(2024, 6, 30)] == 85_777_000_000
    assert date(2024, 9, 30) not in valued


def test_filing_change_without_accessions_refuses_instead_of_selecting() -> None:
    plan = DemoCompleter().complete("What changed in Microsoft's MD&A")
    assert plan.intent is Intent.FILING_CHANGE
    assert plan.older_accession == ""
    assert plan.newer_accession == ""
    result = run_turn("What changed in Microsoft's MD&A", fixture_runtime())
    assert result.intent is Intent.FILING_CHANGE
    assert result.renderer is RendererKind.REFUSE
    assert "accession" in (result.message or "").lower()


def test_guided_filing_change_story_pins_both_accessions() -> None:
    _, question = GUIDED_STORIES[-1]
    result = run_turn(question, fixture_runtime())
    assert result.intent is Intent.FILING_CHANGE
    assert result.renderer is RendererKind.TABLE
    assert result.disclosure_changes
    assert {item.older_accession for item in result.disclosure_changes} == {
        FIXTURE_FILING_OLDER
    }
    assert {item.newer_accession for item in result.disclosure_changes} == {
        FIXTURE_FILING_NEWER
    }


def test_hosted_secrets_enable_guarded_fixture_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "environ", {})
    template = Path(__file__).parents[1] / ".streamlit" / "secrets.toml.example"
    secrets = Secrets()
    secrets.merge_programmatic_secrets(tomllib.loads(template.read_text(encoding="utf-8")))

    settings = Settings(_env_file=None)
    assert settings.app_mode is AppMode.FIXTURE
    assert settings.public_demo is True
    assert settings.demo_live_sec is False
    assert settings.allow_public_openai is False
    assert settings.allow_public_tavily is False
    assert settings.sec_cache_dir == Path(".cache/sec")
    assert settings.require_user_agent() == "FinancialAnalystAgent (you@example.com)"
