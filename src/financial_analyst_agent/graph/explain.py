"""Qualitative explanation subgraph.

Typed interface: plan + runtime in, TurnResult out. Does not read conversation history.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from financial_analyst_agent.contracts import Runtime, TurnResult


class ExplainState(TypedDict):
    plan: Any
    runtime: Runtime
    result: TurnResult | None


def _explain_node(state: ExplainState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _explain_turn

    return {"result": _explain_turn(state["plan"], state["runtime"])}


def _build_explain_graph() -> Any:
    builder = StateGraph(ExplainState)
    builder.add_node("explain", _explain_node)
    builder.add_edge(START, "explain")
    builder.add_edge("explain", END)
    return builder.compile()


_EXPLAIN_GRAPH = _build_explain_graph()


def run_qualitative_explanation(plan: Any, runtime: Runtime) -> TurnResult:
    """Execute the qualitative-explanation workflow; return TurnResult."""
    final: ExplainState = _EXPLAIN_GRAPH.invoke(
        {
            "plan": plan,
            "runtime": runtime,
            "result": None,
        }
    )
    result = final["result"]
    if result is None:
        raise RuntimeError("qualitative explanation subgraph produced no result")
    return result
