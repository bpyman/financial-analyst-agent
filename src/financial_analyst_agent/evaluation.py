"""Evaluation suite, run on the recorded runtime, that publishes a portfolio scorecard."""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore
from financial_analyst_agent.turn import Intent, RendererKind, run_turn

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
            expect_values=("32014000000",),
            expect_accessions=("0001193125-26-191507",),
            expect_concepts=("PretaxIncomeLoss",),
        ),
        EvalCase(
            "compare_tsla_gm",
            "intent_routing",
            "TSLA vs GM revenue",
            Intent.COMPARE,
            RendererKind.TABLE,
            expect_tickers=("TSLA", "GM"),
            expect_values=("19335000000", "44019000000"),
        ),
        EvalCase(
            "rank_tech_rd",
            "intent_routing",
            "Top 10 tech companies R&D spend",
            Intent.RANK_AND_LOOKUP,
            RendererKind.TABLE,
            expect_tickers=("AAPL", "MSFT", "GOOG"),
        ),
        EvalCase(
            "refuse_unknown_metric",
            "ambiguity_refusal",
            "What was Microsoft's ROE last quarter?",
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
            "0001193125-25-000099 and 0001193125-26-191507?",
            Intent.FILING_CHANGE,
            RendererKind.TABLE,
            expect_accessions=("0001193125-25-000099", "0001193125-26-191507"),
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
