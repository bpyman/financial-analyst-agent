"""Qualitative explanation subgraph.

Typed interface: plan + runtime in, TurnResult out. Does not read conversation history.
"""

from __future__ import annotations

from typing import Any, TypedDict

from financial_analyst_agent.contracts import Runtime, TurnResult
from financial_analyst_agent.graph.subgraph import SingleNodeGraph


class ExplainState(TypedDict):
    plan: Any
    runtime: Runtime
    grounding_json: str
    result: TurnResult | None


def _explain_node(state: ExplainState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _explain_turn

    return {
        "result": _explain_turn(
            state["plan"],
            state["runtime"],
            grounding_json=state.get("grounding_json", ""),
        )
    }


_EXPLAIN_GRAPH = SingleNodeGraph(
    ExplainState, "explain", _explain_node, label="qualitative explanation"
)


def run_qualitative_explanation(
    plan: Any, runtime: Runtime, *, grounding_json: str = ""
) -> TurnResult:
    """Execute the qualitative-explanation workflow; return TurnResult."""
    return _EXPLAIN_GRAPH.run(
        {"plan": plan, "runtime": runtime, "grounding_json": grounding_json}
    )
