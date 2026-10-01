"""The one-node subgraph shape the qualitative workflows share (ADR 0005).

Each subgraph keeps its own typed state and node; this owns building the
START → node → END graph and reading its result back out.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langgraph.graph import END, START, StateGraph

from financial_analyst_agent.contracts import TurnResult


class SingleNodeGraph:
    def __init__(self, state_type: Any, name: str, node: Any, *, label: str) -> None:
        builder = StateGraph(state_type)
        builder.add_node(name, node)
        builder.add_edge(START, name)
        builder.add_edge(name, END)
        self._graph = builder.compile()
        self._label = label

    def run(self, inputs: Mapping[str, Any]) -> TurnResult:
        final = self._graph.invoke({**inputs, "result": None})
        result: TurnResult | None = final["result"]
        if result is None:
            raise RuntimeError(f"{self._label} subgraph produced no result")
        return result
