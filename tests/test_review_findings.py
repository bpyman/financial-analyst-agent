"""Regressions for the PRD/ADR review findings, run on the recorded runtime."""

from __future__ import annotations

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind, Runtime
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.turn import run_turn


@pytest.fixture(scope="module")
def runtime() -> Runtime:
    return recorded_runtime()


def test_a_rejected_comparison_is_labelled_a_comparison(runtime: Runtime) -> None:
    # Story 32: a refusal names the analysis asked for, not a default lookup.
    result = run_turn("compare Apple and Microsoft revenue in Q3 FY2040", runtime)

    assert result.renderer is RendererKind.REFUSE
    assert result.intent is Intent.COMPARE
