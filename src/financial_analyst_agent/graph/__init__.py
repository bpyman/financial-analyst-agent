"""Parent graph for closed analysis workflows (migration steps 1–2).

Edges are fixed and typed. The model still selects a closed intent upstream;
it does not choose nodes or chain tools. Graph internals are not a test surface.

Structured analysis (lookup/compare/rank/rank_and_lookup) runs as nodes on the
parent. Qualitative explanation, current events, and exploratory research are
separate subgraphs behind small typed interfaces; the parent dispatches to them.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from financial_analyst_agent.contracts import Intent, Runtime, TurnResult
from financial_analyst_agent.graph.explain import run_qualitative_explanation
from financial_analyst_agent.graph.exploratory import run_exploratory_research
from financial_analyst_agent.graph.news import run_current_events


class WorkflowRunState(TypedDict):
    plan: Any
    runtime: Runtime
    query: str
    grounding_json: str
    result: TurnResult | None


def _lookup_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _lookup_turn

    return {"result": _lookup_turn(state["plan"], state["runtime"])}


def _compare_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _compare_turn

    return {"result": _compare_turn(state["plan"], state["runtime"])}


def _rank_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _rank_turn

    return {"result": _rank_turn(state["plan"], state["runtime"])}


def _rank_and_lookup_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _rank_and_lookup_turn

    return {"result": _rank_and_lookup_turn(state["plan"], state["runtime"])}


def _explain_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    return {
        "result": run_qualitative_explanation(
            state["plan"],
            state["runtime"],
            grounding_json=state.get("grounding_json", ""),
        )
    }


def _news_and_explain_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    return {"result": run_current_events(state["query"], state["runtime"])}


def _exploratory_research_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    return {"result": run_exploratory_research(state["query"], state["runtime"])}


def _filing_change_node(state: WorkflowRunState) -> dict[str, TurnResult]:
    from financial_analyst_agent.filing_change import run_filing_change

    plan = state["plan"]
    action = getattr(plan, "action", plan)
    return {"result": run_filing_change(action, state["runtime"], query=state.get("query", ""))}


# Each closed intent is one node named after its value.
_NODES: dict[Intent, Any] = {
    Intent.LOOKUP: _lookup_node,
    Intent.COMPARE: _compare_node,
    Intent.RANK: _rank_node,
    Intent.RANK_AND_LOOKUP: _rank_and_lookup_node,
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
    """Execute one closed workflow via the parent graph; return TurnResult.

    ``grounding_json`` is optional deterministic analysis already on the thread
    (injected by the conversation seam). Subgraphs still do not read history.
    """
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
