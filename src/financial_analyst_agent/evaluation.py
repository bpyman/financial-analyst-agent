"""Evaluation suite, run on the recorded runtime, that publishes a portfolio scorecard."""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from financial_analyst_agent.contracts import Intent, RendererKind
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.news import FIXTURE_NEWS_QUERY
from financial_analyst_agent.presentation import is_derived, present_turn
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore
from financial_analyst_agent.turn import run_turn

SCORECARD_PATH = Path("docs/evaluation/scorecard.md")
SCORECARD_JSON_PATH = Path("docs/evaluation/scorecard.json")


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: str
    query: str
    expect_intent: Intent | None = None
    expect_renderer: RendererKind | None = None
    follow_up: str | None = None
    expect_tickers: tuple[str, ...] = ()
    expect_companies: tuple[str, ...] = ()
    expect_values: tuple[str, ...] = ()
    expect_accessions: tuple[str, ...] = ()
    expect_concepts: tuple[str, ...] = ()
    invent_numbers: bool = False
    expect_lock_extras: bool = False
    # Later turns of the same conversation; checks apply to the last answer.
    turns: tuple[str, ...] = ()
    # Tickers in this order, first rows of the answer's table.
    expect_order: tuple[str, ...] = ()
    expect_ordered_by: str | None = None
    min_rows: int = 0
    expect_banner: str = ""
    expect_message: str = ""
    expect_candidates: tuple[str, ...] = ()
    # The chart's title on screen ("Growth", "Trend", "Comparison").
    expect_chart: str = ""
    # An end date (ISO) whose figure must be marked derived, as a fiscal Q4 is.
    expect_derived_end: str = ""
    expect_trends: int = 0
    # A news answer cites its sources: at least one, each with a title and a link.
    expect_citations: bool = False
    # Every row's quarter, as (start, end) ISO dates.
    expect_period: tuple[str, str] | None = None


class _InventingEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return "Healthcare AI will grow 47 percent next year."


def _cases() -> tuple[EvalCase, ...]:
    return (
        EvalCase(
            "lookup_msft_pretax",
            "intent_routing",
            "Microsoft pre-tax income",
            Intent.LOOKUP,
            RendererKind.TABLE,
            expect_tickers=("MSFT",),
            expect_values=("44047000000",),
            # The latest quarter is fiscal Q4: the 10-K's year less the 10-Q's nine months.
            expect_derived_end="2026-06-30",
            expect_accessions=("0001193125-26-323660",),
            expect_concepts=(
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
                "ExtraordinaryItemsNoncontrollingInterest",
            ),
        ),
        EvalCase(
            "compare_tsla_gm",
            "intent_routing",
            "TSLA vs GM revenue",
            Intent.COMPARE,
            RendererKind.TABLE,
            expect_tickers=("TSLA", "GM"),
            expect_values=("28236000000", "48026000000"),
            expect_period=("2026-04-01", "2026-06-30"),
        ),
        EvalCase(
            "rank_tech_rd",
            "intent_routing",
            "Top 10 tech companies R&D spend",
            Intent.RANK_AND_LOOKUP,
            RendererKind.TABLE,
            # The snapshot's ten largest technology companies, each with its R&D.
            expect_order=(
                "NVDA", "AAPL", "MSFT", "AVGO", "MU", "AMD", "INTC", "PLTR", "CSCO", "ORCL",
            ),  # fmt: skip
            expect_values=(
                "7054000000", "11729000000", "9997000000", "2895000000", "1316000000",
                "2528000000", "3368000000", "192513000", "2431000000", "2401000000",
            ),  # fmt: skip
        ),
        EvalCase(
            "refuse_unknown_metric",
            "ambiguity_refusal",
            "What was Microsoft's ROA last quarter?",
            Intent.LOOKUP,
            RendererKind.REFUSE,
        ),
        EvalCase(
            "clarify_profit",
            "ambiguity_refusal",
            "What was Microsoft's profit?",
            Intent.LOOKUP,
            RendererKind.CLARIFY,
        ),
        EvalCase(
            "follow_up_add_apple",
            "stateful_follow_up",
            "What was Microsoft's latest quarterly revenue?",
            Intent.LOOKUP,
            RendererKind.TABLE,
            follow_up="add Apple",
            expect_tickers=("MSFT",),
            expect_companies=("Apple Inc.",),
        ),
        EvalCase(
            "numeral_lock_explain",
            "numeral_lock",
            "How can AI disrupt healthcare?",
            Intent.EXPLAIN,
            RendererKind.ESSAY,
        ),
        EvalCase(
            "numeral_lock_invented_number",
            "numeral_lock",
            "How can AI disrupt healthcare?",
            Intent.EXPLAIN,
            RendererKind.REFUSE,
            invent_numbers=True,
            expect_lock_extras=True,
        ),
        EvalCase(
            "filing_change_mda",
            "filing_change",
            "What changed in Microsoft's MD&A between "
            "0000950170-25-061046 and 0001193125-26-191507?",
            Intent.FILING_CHANGE,
            RendererKind.TABLE,
            expect_accessions=("0000950170-25-061046", "0001193125-26-191507"),
        ),
        # Periods and fiscal calendars
        EvalCase(
            "window_four_quarters",
            "periods_and_calendars",
            "Microsoft revenue over the last four quarters",
            Intent.LOOKUP,
            RendererKind.TABLE,
            min_rows=4,
            expect_values=("90007000000", "82886000000", "81273000000", "77673000000"),
            # Microsoft's fiscal Q4 is the 10-K's year less the 10-Q's nine months.
            expect_derived_end="2026-06-30",
        ),
        EvalCase(
            "named_fiscal_quarter",
            "periods_and_calendars",
            "Apple diluted EPS in Q3 FY2025",
            Intent.LOOKUP,
            RendererKind.TABLE,
            expect_values=("1.57",),
            expect_banner="Q3 FY2025 ended Jun 28, 2025",
        ),
        EvalCase(
            "calendars_differ",
            "periods_and_calendars",
            "Compare Nvidia and AMD revenue over the last four quarters",
            Intent.COMPARE,
            RendererKind.TABLE,
            expect_tickers=("NVDA", "AMD"),
            min_rows=8,
            expect_banner="fiscal quarters end on",
        ),
        EvalCase(
            "unreported_future_quarter",
            "periods_and_calendars",
            "Microsoft revenue Q1 2030",
            Intent.LOOKUP,
            RendererKind.REFUSE,
            expect_message="has not been reported yet",
        ),
        EvalCase(
            "sub_quarter_period",
            "periods_and_calendars",
            "Apple revenue last month",
            Intent.LOOKUP,
            RendererKind.TABLE,
            expect_banner="Filings report quarters",
        ),
        # Growth, margins and overviews
        EvalCase(
            "growth_chart",
            "growth_and_trends",
            "Microsoft revenue year over year",
            Intent.LOOKUP,
            RendererKind.TABLE,
            expect_chart="Growth",
        ),
        EvalCase(
            "growth_lines_two_companies",
            "growth_and_trends",
            "Compare Microsoft and Apple revenue growth over the last four quarters",
            Intent.COMPARE,
            RendererKind.TABLE,
            expect_tickers=("MSFT", "AAPL"),
            expect_chart="Growth",
        ),
        EvalCase(
            "overview_with_trends",
            "growth_and_trends",
            "How is Nvidia doing?",
            Intent.LOOKUP,
            RendererKind.TABLE,
            expect_values=("96221000000", "59688000000"),
            expect_trends=2,
        ),
        EvalCase(
            "formula_margin",
            "growth_and_trends",
            "Compare Eli Lilly and Merck net margins",
            Intent.COMPARE,
            RendererKind.TABLE,
            expect_tickers=("LLY", "MRK"),
        ),
        # Rankings and membership
        EvalCase(
            "ranking_ordered_by_metric",
            "rankings",
            "Top 5 semiconductor companies by revenue",
            Intent.RANK_AND_LOOKUP,
            RendererKind.TABLE,
            expect_order=("NVDA", "MU", "AVGO", "INTC", "AMD"),
            expect_ordered_by="revenue",
        ),
        EvalCase(
            "ranking_by_market_cap",
            "rankings",
            "Top 5 banks by market cap",
            Intent.RANK_AND_LOOKUP,
            RendererKind.TABLE,
            expect_order=("JPM", "BAC", "WFC"),
        ),
        EvalCase(
            "fund_is_not_a_company",
            "rankings",
            "SPY revenue",
            Intent.LOOKUP,
            RendererKind.REFUSE,
        ),
        # Clarification and refusal
        EvalCase(
            "clarify_income",
            "ambiguity_refusal",
            "Apple income",
            Intent.LOOKUP,
            RendererKind.CLARIFY,
            expect_candidates=("net_income", "operating_income"),
        ),
        EvalCase(
            "advice_declined",
            "ambiguity_refusal",
            "Should I buy Nvidia stock?",
            Intent.LOOKUP,
            RendererKind.REFUSE,
            expect_message="investment advice",
        ),
        EvalCase(
            "off_topic_refused",
            "ambiguity_refusal",
            "What's the weather?",
            Intent.LOOKUP,
            RendererKind.REFUSE,
        ),
        # Follow-ups edit the analysis
        EvalCase(
            "follow_up_metric_and_company",
            "stateful_follow_up",
            "Microsoft revenue over the last four quarters",
            turns=("add Apple", "now add operating margin"),
            expect_tickers=("MSFT", "AAPL"),
            min_rows=8,
        ),
        EvalCase(
            "follow_up_sort",
            "stateful_follow_up",
            "Compare Microsoft, Apple and Nvidia revenue",
            turns=("sort by revenue",),
            expect_order=("AAPL", "NVDA", "MSFT"),
        ),
        EvalCase(
            "follow_up_swap_company",
            "stateful_follow_up",
            "Compare JPM and BAC net income",
            turns=("what about Goldman?",),
            expect_tickers=("GS",),
        ),
        EvalCase(
            "follow_up_start_over",
            "stateful_follow_up",
            "Compare Apple and Microsoft revenue",
            turns=("start over",),
            expect_message="Started over",
        ),
        # Filings and news
        EvalCase(
            "filing_change_latest",
            "filing_change",
            "What changed in Microsoft's latest 10-Q?",
            Intent.FILING_CHANGE,
            RendererKind.TABLE,
        ),
        EvalCase(
            "news_kept_apart",
            "news",
            FIXTURE_NEWS_QUERY,
            Intent.NEWS_AND_EXPLAIN,
            expect_banner="not from SEC filings",
            expect_citations=True,
        ),
    )


def _check_result(case: EvalCase, result: Any) -> str:
    if case.expect_intent is not None and result.intent is not case.expect_intent:
        return f"intent {result.intent}"
    if case.expect_renderer is not None and result.renderer is not case.expect_renderer:
        return f"renderer {result.renderer}"
    if case.expect_lock_extras:
        if not result.numeral_lock_extras:
            return "expected numeral lock extras"
    elif result.numeral_lock_extras:
        return "numeral lock extras"
    have_tickers = {row.ticker for row in result.table_rows}
    missing_tickers = [ticker for ticker in case.expect_tickers if ticker not in have_tickers]
    if missing_tickers:
        return f"missing tickers {missing_tickers}"
    have_companies = {row.company_name for row in result.table_rows}
    missing_companies = [
        name for name in case.expect_companies if name not in have_companies
    ]
    if missing_companies:
        return f"missing companies {missing_companies}"
    have_values = {str(row.value) for row in result.table_rows if row.value is not None}
    missing_values = [value for value in case.expect_values if value not in have_values]
    if missing_values:
        return f"missing values {missing_values}"
    have_accessions = {row.accession_number for row in result.table_rows} | {
        change.older_accession for change in result.disclosure_changes
    } | {change.newer_accession for change in result.disclosure_changes}
    missing_accessions = [
        accession for accession in case.expect_accessions if accession not in have_accessions
    ]
    if missing_accessions:
        return f"missing accessions {missing_accessions}"
    have_concepts = {row.concept for row in result.table_rows}
    missing_concepts = [concept for concept in case.expect_concepts if concept not in have_concepts]
    if missing_concepts:
        return f"missing concepts {missing_concepts}"
    rows = result.table_rows
    if len(rows) < case.min_rows:
        return f"{len(rows)} rows, expected at least {case.min_rows}"
    if case.expect_order:
        order = list(dict.fromkeys(row.ticker for row in rows))[: len(case.expect_order)]
        if tuple(order) != case.expect_order:
            return f"order {order}"
    if case.expect_ordered_by is not None and result.ordered_by != case.expect_ordered_by:
        return f"ordered by {result.ordered_by}"
    if case.expect_candidates and tuple(result.candidates) != case.expect_candidates:
        return f"candidates {result.candidates}"
    if case.expect_message and case.expect_message not in (result.message or ""):
        return f"message {result.message!r}"
    shown = present_turn(result)
    if case.expect_banner and not any(case.expect_banner in banner for banner in shown.banners):
        return f"missing banner {case.expect_banner!r}"
    if case.expect_chart and (shown.chart is None or shown.chart.title != case.expect_chart):
        return f"chart {shown.chart.title if shown.chart else None}"
    if case.expect_trends and len(shown.trends) != case.expect_trends:
        return f"{len(shown.trends)} trend charts"
    if case.expect_derived_end and not any(
        row.end_date is not None
        and row.end_date.isoformat() == case.expect_derived_end
        and is_derived(row)
        for row in rows
    ):
        return f"no derived figure ending {case.expect_derived_end}"
    if case.expect_period is not None and any(
        (
            row.start_date.isoformat() if row.start_date else "",
            row.end_date.isoformat() if row.end_date else "",
        )
        != case.expect_period
        for row in rows
        if row.value is not None
    ):
        return f"period not {case.expect_period}"
    if case.expect_citations and not (
        result.citations and all(hit.title and hit.url for hit in result.citations)
    ):
        return "missing citations"
    if case.category == "filing_change" and not result.disclosure_changes:
        return "missing disclosure changes"
    if case.category == "filing_change" and not all(
        change.older_url and change.newer_url for change in result.disclosure_changes
    ):
        return "missing filing citations"
    return ""


def run_suite() -> dict[str, Any]:
    runtime = recorded_runtime()
    rows: list[dict[str, Any]] = []
    for case in _cases():
        started = time.perf_counter()
        passed = True
        detail = ""
        case_runtime = (
            replace(runtime, essay=_InventingEssay()) if case.invent_numbers else runtime
        )
        try:
            if case.follow_up:
                store = EphemeralThreadStore()
                first = run_conversation_turn(
                    "eval", case.query, case_runtime, store=store
                )
                second = run_conversation_turn(
                    "eval", case.follow_up, case_runtime, store=store
                )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                detail = _check_result(
                    EvalCase(
                        case.case_id,
                        case.category,
                        case.query,
                        expect_intent=case.expect_intent,
                        expect_renderer=case.expect_renderer,
                    ),
                    first.result,
                )
                if not detail:
                    if second.result.renderer is RendererKind.REFUSE:
                        detail = "follow-up refused"
                    elif second.analysis_spec is None:
                        detail = "follow-up dropped spec"
                    else:
                        detail = _check_result(
                            EvalCase(
                                case.case_id,
                                case.category,
                                case.follow_up,
                                expect_tickers=case.expect_tickers,
                                expect_companies=case.expect_companies,
                            ),
                            second.result,
                        )
            elif case.turns:
                store = EphemeralThreadStore()
                turn = run_conversation_turn("eval", case.query, case_runtime, store=store)
                for message in case.turns:
                    turn = run_conversation_turn("eval", message, case_runtime, store=store)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                detail = _check_result(case, turn.result)
            else:
                result = run_turn(case.query, case_runtime)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                detail = _check_result(case, result)
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            passed = False
            detail = type(exc).__name__
        if detail:
            passed = False
        rows.append(
            {
                "id": case.case_id,
                "category": case.category,
                "passed": passed,
                "elapsed_ms": elapsed_ms,
                "detail": detail,
            }
        )
    latencies = [row["elapsed_ms"] for row in rows]
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95_index = min(len(latencies_sorted) - 1, int(0.95 * (len(latencies_sorted) - 1)))
    pass_count = sum(1 for row in rows if row["passed"])
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": "recorded DemoCompleter",
        "live_cost_usd": None,
        "pass_count": pass_count,
        "case_count": len(rows),
        "pass_rate": pass_count / len(rows) if rows else 0.0,
        "p50_ms": p50,
        "p95_ms": latencies_sorted[p95_index],
        "mean_ms": statistics.mean(latencies) if latencies else 0,
        "cases": rows,
    }
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Evaluation scorecard",
        "",
        f"Generated `{payload['generated_at']}` against the recorded runtime.",
        "",
        f"- Pass rate: **{payload['pass_count']}/{payload['case_count']}** "
        f"({payload['pass_rate']:.0%})",
        f"- Latency p50 / p95: **{payload['p50_ms']} ms** / **{payload['p95_ms']} ms**",
        "- Approximate live cost per scenario: **not measured** "
        "(published card is the recorded runtime)",
        f"- Planner: `{payload['model']}`",
        "",
        "| Case | Category | Result | ms |",
        "| --- | --- | --- | ---: |",
    ]
    for row in payload["cases"]:
        mark = "pass" if row["passed"] else f"fail ({row['detail']})"
        lines.append(
            f"| `{row['id']}` | {row['category']} | {mark} | {row['elapsed_ms']} |"
        )
    lines.append("")
    lines.append(
        "The cases run on the recorded runtime, so they are repeatable and need no keys. "
        "[Figures checked against their filings](filing-check.md) is the live "
        "counterpart: each figure the window shows, found in the text of the 10-Q it cites."
    )
    lines.append("")
    lines.append(
        "SEC JSON is disk-cached on the live path; retries and 429/5xx backoff live in "
        "`SECClient`. This is not a full production operations report."
    )
    lines.append("")
    return "\n".join(lines)


def write_scorecard(root: Path | None = None) -> dict[str, Any]:
    payload = run_suite()
    base = root or Path()
    markdown_path = base / SCORECARD_PATH
    json_path = base / SCORECARD_JSON_PATH
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    payload = write_scorecard()
    print(f"{payload['pass_count']}/{payload['case_count']} passed")


if __name__ == "__main__":
    main()
