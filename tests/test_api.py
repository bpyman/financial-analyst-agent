"""HTTP seam for the Next.js window (ADR 0006): threads, streamed turns, display records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from financial_analyst_agent.api import create_app
from financial_analyst_agent.config import AppMode, Settings
from financial_analyst_agent.storefront import GUIDED_STORIES

# Keys the web client reads (web/lib/types.ts). Renaming one is a client break.
PRESENTATION_KEYS = {
    "intent",
    "intent_label",
    "banners",
    "traces",
    "citations",
    "fact_card",
    "table",
    "chart",
    "evidence",
    "disclosures",
    "essay",
    "message",
    "candidates",
}


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"app_mode": AppMode.RECORDED, "_env_file": None}
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(_settings(), store_root=tmp_path / "threads"))


def _events(response: Any) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def _new_thread(client: TestClient) -> str:
    response = client.post("/api/threads")
    assert response.status_code == 201
    return str(response.json()["thread_id"])


def _ask(client: TestClient, thread_id: str, message: str) -> dict[str, Any]:
    response = client.post(
        f"/api/threads/{thread_id}/turns", json={"message": message, "recorded": True}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert events[0][0] == "progress"
    kind, data = events[-1]
    assert kind == "thread", data
    assert all(name == "progress" for name, _ in events[:-1])
    return data


def test_meta_serves_storefront_copy_and_snapshot_banner(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert meta["recorded"] == {"default": True, "locked": False}
    assert [story["label"] for story in meta["guided_stories"]] == [
        label for label, _ in GUIDED_STORIES
    ]
    assert meta["snapshot"]["banner"].startswith("Universe snapshot as of ")
    assert meta["metric_groups"][0]["title"] == "Reported (SEC EDGAR)"
    assert "Net income" in meta["metric_groups"][0]["names"]


def test_public_demo_locks_recorded_mode(tmp_path: Path) -> None:
    app = create_app(
        _settings(app_mode=AppMode.LIVE, public_demo=True), store_root=tmp_path
    )
    meta = TestClient(app).get("/api/meta?recorded=false").json()
    assert meta["recorded"] == {"default": True, "locked": True}


def test_unknown_thread_is_empty_and_malformed_id_is_404(client: TestClient) -> None:
    thread_id = _new_thread(client)
    view = client.get(f"/api/threads/{thread_id}").json()
    assert view["turns"] == []
    assert view["pending_clarification"] is False
    assert client.get("/api/threads/..%2Fetc").status_code == 404
    assert client.get("/api/threads/not-a-uuid").status_code == 404


def test_guided_story_streams_a_fact_card_with_formatted_amount(client: TestClient) -> None:
    thread_id = _new_thread(client)
    view = _ask(client, thread_id, GUIDED_STORIES[0][1])
    [turn] = view["turns"]
    presented = turn["presentation"]
    assert set(presented) == PRESENTATION_KEYS
    assert presented["intent"] == "lookup"
    card = presented["fact_card"]
    assert card is not None
    assert card["amount"].startswith("$")
    assert card["form"] == "10-Q"
    assert presented["evidence"][0]["raw_amount"].isdigit()
    assert presented["traces"], "tool traces must reach the client"
    assert view["turn_count"] == 1


def test_follow_up_extends_thread_and_reload_returns_history(client: TestClient) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[1][1])
    view = _ask(client, thread_id, "add Apple")
    assert [turn["message"] for turn in view["turns"]] == [GUIDED_STORIES[1][1], "add Apple"]
    assert "AAPL" in view["spec_chips"]
    chart = view["turns"][-1]["presentation"]["chart"]
    assert chart["kind"] == "line"
    assert chart["value_kind"] == "usd"
    assert chart["metric_label"] == "Revenue"
    assert len(chart["period_labels"]) == len(chart["records"]) == len(chart["amounts"])
    assert chart["period_labels"][0].startswith(("Mar", "Jun", "Sep", "Dec"))
    assert set(chart["series"]) == {"Microsoft Corporation", "Apple Inc."}
    assert all(
        amount.startswith("$") or amount == ""
        for row in chart["amounts"]
        for amount in row.values()
    )
    reloaded = client.get(f"/api/threads/{thread_id}").json()
    assert reloaded == view


def test_ambiguous_metric_offers_live_candidates_on_last_turn_only(client: TestClient) -> None:
    thread_id = _new_thread(client)
    view = _ask(client, thread_id, "What was Google's latest quarterly profit?")
    turn = view["turns"][-1]
    assert view["pending_clarification"] is True
    assert turn["clarify_enabled"] is True
    assert turn["candidate_slugs"] == ["gross_profit", "operating_income", "net_income"]
    assert turn["presentation"]["candidates"] == ["Gross profit", "Operating income", "Net income"]

    answered = _ask(client, thread_id, "net_income")
    assert answered["pending_clarification"] is False
    assert answered["turns"][0]["clarify_enabled"] is False
    assert answered["turns"][-1]["presentation"]["fact_card"] is not None


def test_start_over_clears_thread(client: TestClient) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    assert client.delete(f"/api/threads/{thread_id}").status_code == 204
    assert client.get(f"/api/threads/{thread_id}").json()["turns"] == []


def test_turn_quota_streams_public_error(tmp_path: Path) -> None:
    client = TestClient(
        create_app(_settings(max_turns_per_thread=1), store_root=tmp_path)
    )
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    response = client.post(
        f"/api/threads/{thread_id}/turns", json={"message": "add Apple", "recorded": True}
    )
    kind, data = _events(response)[-1]
    assert kind == "error"
    assert "turn limit" in data["message"]


def test_blank_message_is_rejected(client: TestClient) -> None:
    thread_id = _new_thread(client)
    response = client.post(
        f"/api/threads/{thread_id}/turns", json={"message": "   ", "recorded": True}
    )
    assert response.status_code == 422
