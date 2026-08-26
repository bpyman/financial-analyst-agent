"""Exploratory research subgraph.

Typed interface: analyst query + runtime in, TurnResult out. Does not read
conversation history. Search stays the constrained news wrapper; output is a
labelled research draft with citations and never structured financial rows.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from financial_analyst_agent.contracts import Runtime, TurnResult


class ExploratoryState(TypedDict):
    query: str
    runtime: Runtime
    result: TurnResult | None


def _exploratory_node(state: ExploratoryState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _exploratory_research_turn

    return {"result": _exploratory_research_turn(state["query"], state["runtime"])}


def _build_exploratory_graph() -> Any:
    builder = StateGraph(ExploratoryState)
    builder.add_node("exploratory_research", _exploratory_node)
    builder.add_edge(START, "exploratory_research")
    builder.add_edge("exploratory_research", END)
    return builder.compile()


_EXPLORATORY_GRAPH = _build_exploratory_graph()


def run_exploratory_research(query: str, runtime: Runtime) -> TurnResult:
    """Execute the exploratory research workflow; return TurnResult."""
    final: ExploratoryState = _EXPLORATORY_GRAPH.invoke(
        {
            "query": query,
            "runtime": runtime,
            "result": None,
        }
    )
    result = final["result"]
    if result is None:
        raise RuntimeError("exploratory research subgraph produced no result")
    return result
