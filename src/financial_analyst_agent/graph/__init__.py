"""Closed qualitative and filing workflows, dispatched by the planned intent.

Structured analyses do not come through here: their compiled tasks run through
``spec_turn.TASK_WORKFLOWS``. Edges are fixed and typed; the model selects a
closed intent upstream and does not choose nodes or chain tools.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from financial_analyst_agent.contracts import Intent, Runtime, TurnResult


class WorkflowRunState(TypedDict):
    plan: Any
    runtime: Runtime
    query: str
    grounding_json: str
    result: TurnResult | None


def _explain_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import explain_answer

    return {
        "result": explain_answer(
            state["plan"].topic,
            state["runtime"],
            grounding_json=state.get("grounding_json", ""),
        )
    }


def _news_and_explain_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import current_events_answer

    return {"result": current_events_answer(state["query"], state["runtime"])}


def _exploratory_research_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import exploratory_research_answer

    return {"result": exploratory_research_answer(state["query"], state["runtime"])}


def _filing_change_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.filing_change import run_filing_change

    plan = state["plan"]
    action = getattr(plan, "action", plan)
    return {"result": run_filing_change(action, state["runtime"], query=state.get("query", ""))}


# Each closed intent is one node named after its value.
_NODES: dict[Intent, Any] = {
    Intent.EXPLAIN: _explain_node,
    Intent.NEWS_AND_EXPLAIN: _news_and_explain_node,
    Intent.EXPLORATORY_RESEARCH: _exploratory_research_node,
    Intent.FILING_CHANGE: _filing_change_node,
}


def _route_closed(state: WorkflowRunState) -> str:
    intent = state["plan"].intent
    if intent not in _NODES:
        raise ValueError(f"unsupported closed intent: {intent!r}")
    return str(intent)


def _build_workflow_graph() -> Any:
    builder = StateGraph(WorkflowRunState)
    for intent, node in _NODES.items():
        builder.add_node(intent.value, node)
        builder.add_edge(intent.value, END)
    builder.add_conditional_edges(
        START, _route_closed, {intent.value: intent.value for intent in _NODES}
    )
    return builder.compile()


_WORKFLOW_GRAPH = _build_workflow_graph()


def run_workflow_turn(
    plan: Any,
    runtime: Runtime,
    *,
    query: str = "",
    grounding_json: str = "",
) -> TurnResult:
    """Execute one closed qualitative or filing workflow; return TurnResult."""
    final: WorkflowRunState = _WORKFLOW_GRAPH.invoke(
        {
            "plan": plan,
            "runtime": runtime,
            "query": query,
            "grounding_json": grounding_json,
            "result": None,
        }
    )
    result = final["result"]
    if result is None:
        raise RuntimeError("workflow graph produced no result")
    return result
