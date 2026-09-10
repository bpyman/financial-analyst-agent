"""Provider timing logs include planner and LLM events, not only end-to-end turns."""

import json
import logging

import pytest

from financial_analyst_agent.observability import call_provider
from financial_analyst_agent.runtime import fixture_runtime
from financial_analyst_agent.turn import run_turn


def _events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def test_call_provider_emits_provider_timing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="financial_analyst_agent")
    assert call_provider("planner", lambda: "ok") == "ok"
    providers = {
        event.get("provider") for event in _events(caplog) if event.get("event") == "provider"
    }
    assert "planner" in providers
    assert any(
        event.get("event") == "provider" and "elapsed_ms" in event for event in _events(caplog)
    )


def test_explain_turn_logs_planner_and_llm_timing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="financial_analyst_agent")
    result = run_turn("How can AI disrupt healthcare?", fixture_runtime())
    assert result.essay
    names = {event.get("event") for event in _events(caplog)}
    providers = {
        event.get("provider") for event in _events(caplog) if event.get("event") == "provider"
    }
    assert "conversation_turn" in names
    assert "planner" in providers
    assert "llm" in providers
    assert any(
        event.get("event") == "provider"
        and event.get("thread_id") == "ephemeral"
        and event.get("turn") == 1
        for event in _events(caplog)
    )
