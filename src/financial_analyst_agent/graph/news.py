"""Current-events (news-and-explain) subgraph.

Typed interface: analyst query + runtime in, TurnResult out. Does not read
conversation history. Search stays the constrained news wrapper.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from financial_analyst_agent.contracts import Runtime, TurnResult


class CurrentEventsState(TypedDict):
    query: str
    runtime: Runtime
    result: TurnResult | None


def _current_events_node(state: CurrentEventsState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _news_and_explain_turn

    return {"result": _news_and_explain_turn(state["query"], state["runtime"])}


def _build_current_events_graph() -> Any:
    builder = StateGraph(CurrentEventsState)
    builder.add_node("current_events", _current_events_node)
    builder.add_edge(START, "current_events")
    builder.add_edge("current_events", END)
    return builder.compile()


_CURRENT_EVENTS_GRAPH = _build_current_events_graph()


def run_current_events(query: str, runtime: Runtime) -> TurnResult:
    """Execute the current-events workflow; return TurnResult."""
    final: CurrentEventsState = _CURRENT_EVENTS_GRAPH.invoke(
        {
            "query": query,
            "runtime": runtime,
            "result": None,
        }
    )
    result = final["result"]
    if result is None:
        raise RuntimeError("current-events subgraph produced no result")
    return result
