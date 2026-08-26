"""Contracts must load without pulling in workflow implementations."""

from __future__ import annotations

import sys


def test_contracts_import_without_loading_turn_workflows() -> None:
    dependents = (
        "financial_analyst_agent.turn",
        "financial_analyst_agent.conversation",
        "financial_analyst_agent.thread_store",
        "financial_analyst_agent.contracts",
    )
    for name in list(sys.modules):
        if name in dependents or any(name.startswith(f"{dep}.") for dep in dependents):
            del sys.modules[name]

    import financial_analyst_agent.contracts as contracts

    assert "financial_analyst_agent.turn" not in sys.modules
    assert contracts.Intent.LOOKUP == "lookup"
    assert contracts.RendererKind.TABLE == "table"
    assert "revenue" in contracts.ALLOWED_METRICS
    assert contracts.Runtime is not None
    assert contracts.TurnResult is not None
    assert contracts.NewsHit is not None
    assert contracts.FactsPort is not None


def test_turn_reexports_contract_names() -> None:
    from financial_analyst_agent import turn

    assert turn.Intent is not None
    assert turn.Runtime is not None
    assert turn.TurnResult is not None
    assert turn.ALLOWED_METRICS is not None
    assert turn.SNAPSHOT_METRICS is not None
    assert turn.NewsHit is not None
    assert callable(turn.run_turn)
    assert callable(turn.compare_metrics)
    assert callable(turn.snapshot_compare_rows)
