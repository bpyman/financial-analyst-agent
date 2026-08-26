"""Parent graph for structured analysis workflows (migration step 1).

Edges are fixed and typed. The model still selects a closed intent upstream;
it does not choose nodes or chain tools. Graph internals are not a test surface.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from financial_analyst_agent.contracts import Intent, Runtime, TurnResult

StructuredWorkflow = Literal["lookup", "compare", "rank", "rank_and_lookup"]


class StructuredRunState(TypedDict):
    plan: Any
    runtime: Runtime
    result: TurnResult | None


def _route_structured(state: StructuredRunState) -> StructuredWorkflow:
    intent = state["plan"].intent
    if intent == Intent.LOOKUP:
        return "lookup"
    if intent == Intent.COMPARE:
        return "compare"
    if intent == Intent.RANK:
        return "rank"
    if intent == Intent.RANK_AND_LOOKUP:
        return "rank_and_lookup"
    raise ValueError(f"unsupported structured intent: {intent!r}")


def _lookup_node(state: StructuredRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _lookup_turn

    return {"result": _lookup_turn(state["plan"], state["runtime"])}


def _compare_node(state: StructuredRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _compare_turn

    return {"result": _compare_turn(state["plan"], state["runtime"])}


def _rank_node(state: StructuredRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _rank_turn

    return {"result": _rank_turn(state["plan"], state["runtime"])}


def _rank_and_lookup_node(state: StructuredRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _rank_and_lookup_turn

    return {"result": _rank_and_lookup_turn(state["plan"], state["runtime"])}


def _build_structured_graph() -> Any:
    builder = StateGraph(StructuredRunState)
    builder.add_node("lookup", _lookup_node)
    builder.add_node("compare", _compare_node)
    builder.add_node("rank", _rank_node)
    builder.add_node("rank_and_lookup", _rank_and_lookup_node)
    builder.add_conditional_edges(
        START,
        _route_structured,
        {
            "lookup": "lookup",
            "compare": "compare",
            "rank": "rank",
            "rank_and_lookup": "rank_and_lookup",
        },
    )
    builder.add_edge("lookup", END)
    builder.add_edge("compare", END)
    builder.add_edge("rank", END)
    builder.add_edge("rank_and_lookup", END)
    return builder.compile()


_STRUCTURED_GRAPH = _build_structured_graph()


def run_structured_turn(plan: Any, runtime: Runtime) -> TurnResult:
    """Execute one structured workflow via the parent graph; return TurnResult."""
    final: StructuredRunState = _STRUCTURED_GRAPH.invoke(
        {
            "plan": plan,
            "runtime": runtime,
            "result": None,
        }
    )
    result = final["result"]
    if result is None:
        raise RuntimeError("structured graph produced no result")
    return result
