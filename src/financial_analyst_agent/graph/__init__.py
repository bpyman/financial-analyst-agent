"""Parent graph for closed analysis workflows (migration steps 1–2).

Edges are fixed and typed. The model still selects a closed intent upstream;
it does not choose nodes or chain tools. Graph internals are not a test surface.

Structured analysis (lookup/compare/rank/rank_and_lookup) runs as nodes on the
parent. Qualitative explanation, current events, and exploratory research are
separate subgraphs behind small typed interfaces; the parent dispatches to them.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from financial_analyst_agent.contracts import Intent, Runtime, TurnResult
from financial_analyst_agent.graph.explain import run_qualitative_explanation
from financial_analyst_agent.graph.exploratory import run_exploratory_research
from financial_analyst_agent.graph.news import run_current_events

ClosedWorkflow = Literal[
    "lookup",
    "compare",
    "rank",
    "rank_and_lookup",
    "explain",
    "news_and_explain",
    "exploratory_research",
    "filing_change",
]


class WorkflowRunState(TypedDict):
    plan: Any
    runtime: Runtime
    query: str
    grounding_json: str
    result: TurnResult | None


def _route_closed(state: WorkflowRunState) -> ClosedWorkflow:
    intent = state["plan"].intent
    if intent == Intent.LOOKUP:
        return "lookup"
    if intent == Intent.COMPARE:
        return "compare"
    if intent == Intent.RANK:
        return "rank"
    if intent == Intent.RANK_AND_LOOKUP:
        return "rank_and_lookup"
    if intent == Intent.EXPLAIN:
        return "explain"
    if intent == Intent.NEWS_AND_EXPLAIN:
        return "news_and_explain"
    if intent == Intent.EXPLORATORY_RESEARCH:
        return "exploratory_research"
    if intent == Intent.FILING_CHANGE:
        return "filing_change"
    raise ValueError(f"unsupported closed intent: {intent!r}")


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
    return {"result": run_filing_change(action, state["runtime"])}


def _build_workflow_graph() -> Any:
    builder = StateGraph(WorkflowRunState)
    builder.add_node("lookup", _lookup_node)
    builder.add_node("compare", _compare_node)
    builder.add_node("rank", _rank_node)
    builder.add_node("rank_and_lookup", _rank_and_lookup_node)
    builder.add_node("explain", _explain_node)
    builder.add_node("news_and_explain", _news_and_explain_node)
    builder.add_node("exploratory_research", _exploratory_research_node)
    builder.add_node("filing_change", _filing_change_node)
    builder.add_conditional_edges(
        START,
        _route_closed,
        {
            "lookup": "lookup",
            "compare": "compare",
            "rank": "rank",
            "rank_and_lookup": "rank_and_lookup",
            "explain": "explain",
            "news_and_explain": "news_and_explain",
            "exploratory_research": "exploratory_research",
            "filing_change": "filing_change",
        },
    )
    builder.add_edge("lookup", END)
    builder.add_edge("compare", END)
    builder.add_edge("rank", END)
    builder.add_edge("rank_and_lookup", END)
    builder.add_edge("explain", END)
    builder.add_edge("news_and_explain", END)
    builder.add_edge("exploratory_research", END)
    builder.add_edge("filing_change", END)
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


def run_structured_turn(plan: Any, runtime: Runtime) -> TurnResult:
    """Execute one structured workflow via the parent graph; return TurnResult."""
    return run_workflow_turn(plan, runtime)
