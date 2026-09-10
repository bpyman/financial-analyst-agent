"""Fixture evaluation suite used to publish a portfolio scorecard."""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.runtime import fixture_runtime
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


def _cases() -> tuple[EvalCase, ...]:
    return (
        EvalCase(
            "lookup_msft_pretax",
            "intent_routing",
            "Microsoft pre-tax income",
            Intent.LOOKUP,
            RendererKind.TABLE,
        ),
        EvalCase(
            "compare_tsla_gm",
            "intent_routing",
            "TSLA vs GM revenue",
            Intent.COMPARE,
            RendererKind.TABLE,
        ),
        EvalCase(
            "rank_tech_rd",
            "intent_routing",
            "Top 10 tech companies R&D spend",
            Intent.RANK_AND_LOOKUP,
            RendererKind.TABLE,
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
        ),
        EvalCase(
            "numeral_lock_explain",
            "numeral_lock",
            "How can AI disrupt healthcare?",
            Intent.EXPLAIN,
            RendererKind.ESSAY,
        ),
        EvalCase(
            "filing_change_mda",
            "filing_change",
            "What changed in Microsoft's MD&A between "
            "0001193125-25-000099 and 0001193125-26-191507?",
            Intent.FILING_CHANGE,
            RendererKind.TABLE,
        ),
    )


def run_suite() -> dict[str, Any]:
    runtime = fixture_runtime()
    rows: list[dict[str, Any]] = []
    for case in _cases():
        started = time.perf_counter()
        passed = True
        detail = ""
        try:
            if case.follow_up:
                store = EphemeralThreadStore()
                first = run_conversation_turn("eval", case.query, runtime, store=store)
                second = run_conversation_turn("eval", case.follow_up, runtime, store=store)
                result = second.result
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                if case.expect_intent is not None and first.result.intent is not case.expect_intent:
                    passed = False
                    detail = f"first intent {first.result.intent}"
                elif result.renderer is RendererKind.REFUSE:
                    passed = False
                    detail = "follow-up refused"
                elif second.analysis_spec is None:
                    passed = False
                    detail = "follow-up dropped spec"
            else:
                result = run_turn(case.query, runtime)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                if case.expect_intent is not None and result.intent is not case.expect_intent:
                    passed = False
                    detail = f"intent {result.intent}"
                if case.expect_renderer is not None and result.renderer is not case.expect_renderer:
                    passed = False
                    detail = f"renderer {result.renderer}"
                if result.numeral_lock_extras:
                    passed = False
                    detail = "numeral lock extras"
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            passed = False
            detail = type(exc).__name__
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
        "model": "fixture DemoCompleter",
        "live_cost_usd": 0.0,
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
        f"Generated `{payload['generated_at']}` against the fixture runtime.",
        "",
        f"- Pass rate: **{payload['pass_count']}/{payload['case_count']}** "
        f"({payload['pass_rate']:.0%})",
        f"- Latency p50 / p95: **{payload['p50_ms']} ms** / **{payload['p95_ms']} ms**",
        f"- Approximate live cost per scenario: **${payload['live_cost_usd']:.2f}** "
        "(fixture path; live OpenAI/Tavily is not billed here)",
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
