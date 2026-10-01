"""Exploratory research subgraph.

Typed interface: analyst query + runtime in, TurnResult out. Does not read
conversation history. Search stays the constrained news wrapper; output is a
labelled research draft with citations and never structured financial rows.
"""

from __future__ import annotations

from typing import TypedDict

from financial_analyst_agent.contracts import Runtime, TurnResult
from financial_analyst_agent.graph.subgraph import SingleNodeGraph


class ExploratoryState(TypedDict):
    query: str
    runtime: Runtime
    result: TurnResult | None


def _exploratory_node(state: ExploratoryState) -> dict[str, TurnResult]:
    from financial_analyst_agent.turn import _exploratory_research_turn

    return {"result": _exploratory_research_turn(state["query"], state["runtime"])}


_EXPLORATORY_GRAPH = SingleNodeGraph(
    ExploratoryState,
    "exploratory_research",
    _exploratory_node,
    label="exploratory research",
)


def run_exploratory_research(query: str, runtime: Runtime) -> TurnResult:
    """Execute the exploratory research workflow; return TurnResult."""
    return _EXPLORATORY_GRAPH.run({"query": query, "runtime": runtime})
