"""Smoke the fixture-first audience window and first guided story."""

from datetime import date

from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.presentation import present_turn
from financial_analyst_agent.runtime import (
    FIXTURE_FILING_NEWER,
    FIXTURE_FILING_OLDER,
    DemoCompleter,
    recorded_runtime,
)
from financial_analyst_agent.storefront import GUIDED_STORIES
from financial_analyst_agent.thread_store import EphemeralThreadStore
from financial_analyst_agent.turn import Intent, RendererKind, run_turn


def test_first_guided_story_returns_a_table() -> None:
    _, question = GUIDED_STORIES[0]
    result = run_turn(question, recorded_runtime())
    assert result.renderer is RendererKind.TABLE
    assert result.table_rows
    assert result.table_rows[0].value is not None


def test_fixture_apple_last_four_quarters_revenue_has_values() -> None:
    result = run_turn(
        "What was Apple's quarterly revenue over the last four quarters?",
        recorded_runtime(),
    )
    rows = [row for row in result.table_rows if row.comparison is None]
    assert result.renderer is RendererKind.TABLE
    assert [row.ticker for row in rows] == ["AAPL"] * 4
    assert all(row.value is not None for row in rows)


def test_add_apple_after_microsoft_four_quarters_returns_apple_revenue() -> None:
    store = EphemeralThreadStore()
    runtime = recorded_runtime()
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
    result = run_turn("What changed in Microsoft's MD&A", recorded_runtime())
    assert result.intent is Intent.FILING_CHANGE
    assert result.renderer is RendererKind.REFUSE
    assert "accession" in (result.message or "").lower()


def test_guided_filing_change_story_pins_both_accessions() -> None:
    _, question = GUIDED_STORIES[-1]
    result = run_turn(question, recorded_runtime())
    assert result.intent is Intent.FILING_CHANGE
    assert result.renderer is RendererKind.TABLE
    assert result.disclosure_changes
    assert {item.older_accession for item in result.disclosure_changes} == {
        FIXTURE_FILING_OLDER
    }
    assert {item.newer_accession for item in result.disclosure_changes} == {
        FIXTURE_FILING_NEWER
    }



def test_compare_four_quarters_story_presents_each_quarter_on_its_own() -> None:
    presented = present_turn(run_turn(GUIDED_STORIES[1][1], recorded_runtime()))

    headers = [
        trace.header
        for trace in presented.traces
        if trace.header.startswith("Looked up Microsoft · Revenue")
    ]
    assert len(headers) == len(set(headers)) == 4
    assert all("get_financials" not in header for header in headers)
    labels = [item.label for item in presented.evidence]
    assert len(labels) == len(set(labels)) == 4
    september = next(
        item for item in presented.evidence if item.period_label == "Jul 1, 2024 – Sep 30, 2024"
    )
    assert september.raw_amount == "65585000000"
    assert "Sep 30, 2024" in september.label


def test_filing_change_story_presents_each_changed_section() -> None:
    presented = present_turn(run_turn(GUIDED_STORIES[3][1], recorded_runtime()))

    assert [(item.section_label, item.change_kind) for item in presented.disclosures] == [
        ("Management's Discussion and Analysis", "changed"),
        ("Risk Factors", "changed"),
    ]
