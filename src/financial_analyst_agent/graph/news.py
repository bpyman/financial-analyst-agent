"""Current-events (news-and-explain) subgraph.

Typed interface: analyst query + runtime in, TurnResult out. Does not read
conversation history. Search stays the constrained news wrapper.
"""

from __future__ import annotations

from typing import TypedDict

from financial_analyst_agent.contracts import Runtime, TurnResult
from financial_analyst_agent.graph.subgraph import SingleNodeGraph


class CurrentEventsState(TypedDict):
    query: str
    runtime: Runtime
    result: TurnResult | None


def _current_events_node(state: CurrentEventsState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _news_and_explain_turn

    return {"result": _news_and_explain_turn(state["query"], state["runtime"])}


_CURRENT_EVENTS_GRAPH = SingleNodeGraph(
    CurrentEventsState, "current_events", _current_events_node, label="current-events"
)


def run_current_events(query: str, runtime: Runtime) -> TurnResult:
    """Execute the current-events workflow; return TurnResult."""
    return _CURRENT_EVENTS_GRAPH.run({"query": query, "runtime": runtime})
