"""Smoke the fixture-first audience window and first guided story."""

from datetime import date

from financial_analyst_agent.contracts import Intent, RendererKind
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.presentation import present_turn
from financial_analyst_agent.runtime import (
    RECORDED_FILING_NEWER,
    RECORDED_FILING_OLDER,
    DemoCompleter,
    recorded_runtime,
)
from financial_analyst_agent.storefront import GUIDED_STORIES
from financial_analyst_agent.thread_store import EphemeralThreadStore
from financial_analyst_agent.turn import run_turn


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
    # Apple's 52/53-week quarters end a few days before Microsoft's; its fiscal
    # fourth quarter (to September) is derived from the 10-K (ADR 0007).
    assert valued == {
        date(2026, 6, 27): 109_417_000_000,
        date(2026, 3, 28): 111_184_000_000,
        date(2025, 12, 27): 143_756_000_000,
        date(2025, 9, 27): 102_466_000_000,
    }


def test_filing_change_without_accessions_compares_the_same_quarter_a_year_apart() -> None:
    plan = DemoCompleter().complete("What changed in Microsoft's MD&A")
    assert plan.intent is Intent.FILING_CHANGE
    assert plan.older_accession == ""
    assert plan.newer_accession == ""
    result = run_turn("What changed in Microsoft's MD&A", recorded_runtime())
    assert result.intent is Intent.FILING_CHANGE
    assert result.renderer is RendererKind.TABLE
    # Deterministic code picks the filings, and says which.
    assert {item.older_accession for item in result.disclosure_changes} == {
        RECORDED_FILING_OLDER
    }
    assert {item.newer_accession for item in result.disclosure_changes} == {
        RECORDED_FILING_NEWER
    }
    assert any("same quarter" in banner or "latest 10-Q" in banner for banner in result.banners)


def test_filing_change_with_one_accession_refuses() -> None:
    result = run_turn(
        f"What changed in Microsoft's MD&A since {RECORDED_FILING_OLDER}", recorded_runtime()
    )
    assert result.renderer is RendererKind.REFUSE
    assert "accession" in (result.message or "").lower()


def test_guided_filing_change_story_pins_both_accessions() -> None:
    _, question = GUIDED_STORIES[-1]
    result = run_turn(question, recorded_runtime())
    assert result.intent is Intent.FILING_CHANGE
    assert result.renderer is RendererKind.TABLE
    assert result.disclosure_changes
    assert {item.older_accession for item in result.disclosure_changes} == {
        RECORDED_FILING_OLDER
    }
    assert {item.newer_accession for item in result.disclosure_changes} == {
        RECORDED_FILING_NEWER
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
    # Four quarters, plus the 10-K year and 10-Q nine months behind the derived Q4.
    assert len(labels) == len(set(labels)) == 6
    september = next(
        item for item in presented.evidence if item.period_label == "Jul 1, 2025 – Sep 30, 2025"
    )
    assert september.raw_amount == "77673000000"
    assert "Sep 30, 2025" in september.label


def test_filing_change_story_presents_each_changed_section() -> None:
    presented = present_turn(run_turn(GUIDED_STORIES[3][1], recorded_runtime()))

    order = ["Management's Discussion and Analysis", "Risk Factors"]
    sections = [item.section_label for item in presented.disclosures]
    assert sections == sorted(sections, key=order.index)
    assert set(sections) == set(order)
    # Unrelated paragraphs in one place are one removed and one added, not an edit.
    kinds = {item.change_kind for item in presented.disclosures}
    assert "changed" in kinds and kinds <= {"changed", "added", "removed"}
