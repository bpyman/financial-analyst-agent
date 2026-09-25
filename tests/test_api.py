"""HTTP seam for the Next.js window (ADR 0006): threads, streamed turns, display records."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from financial_analyst_agent import api
from financial_analyst_agent.api import create_app
from financial_analyst_agent.config import AppMode, Settings
from financial_analyst_agent.contracts import Runtime, RuntimeKind
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.runtime import recorded_runtime, resolve_runtime_kind
from financial_analyst_agent.storefront import (
    EXAMPLE_QUERY,
    GUIDED_STORIES,
    PUBLIC_FAILURE_MESSAGE,
)
from financial_analyst_agent.thread_store import LocalThreadStore

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
    "clarify_prompt",
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


def _new_thread(client: TestClient, runtime: str | None = None) -> str:
    body = None if runtime is None else {"runtime": runtime}
    response = client.post("/api/threads", json=body)
    assert response.status_code == 201
    return str(response.json()["thread_id"])


def _post_turn(client: TestClient, thread_id: str, message: str) -> Any:
    return client.post(f"/api/threads/{thread_id}/turns", json={"message": message})


def _ask(client: TestClient, thread_id: str, message: str) -> dict[str, Any]:
    response = _post_turn(client, thread_id, message)
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
    assert meta["runtime_copy"]["recorded"].startswith("Recorded runtime — ")
    assert meta["runtime_copy"]["locked"] == "Live runtime is off on the public demo"


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
    assert turn["presentation"]["clarify_prompt"] == "Which metric do you mean?"

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
    kind, data = _events(_post_turn(client, thread_id, "add Apple"))[-1]
    assert kind == "error"
    assert "turn limit" in data["message"]


def test_meta_serves_the_capability_catalog_and_example_query(client: TestClient) -> None:
    meta = client.get("/api/meta").json()

    assert meta["example_query"] == EXAMPLE_QUERY
    descriptions = [item["description"] for item in meta["capabilities"]]
    assert descriptions == [
        "Look up quarterly 10-Q financial facts or market cap for any "
        "operating publicly-listed US company",
        "Compare companies on metrics, rank by market cap, or combine rank and lookup",
        "Access and analyze relevant financial news linked to specific companies",
        "Answer general queries and provide qualitative industry analysis",
        "Stay on the same thread to extend the current analysis, or start a new one",
    ]
    examples = [example for item in meta["capabilities"] for example in item["examples"]]
    assert examples == [
        "What was Microsoft's latest quarterly revenue?",
        "What is Apple's market cap?",
        "Compare Eli Lilly and Merck net margins",
        "What are the top 10 tech companies and R&D spend for each?",
        "What's going on with Eli Lilly's obesity drugs?",
        "How could AI change bank underwriting?",
        "add Apple",
        "now add operating margin",
        "make that the last four quarters",
        "show year-over-year",
    ]
    groups = {group["title"]: group["names"] for group in meta["metric_groups"]}
    assert list(groups) == ["Reported (SEC EDGAR)", "Calculated", "Daily snapshot (FMP)"]
    assert groups["Reported (SEC EDGAR)"][0] == "Revenue"
    assert "Gross margin" in groups["Calculated"]
    assert groups["Daily snapshot (FMP)"] == ["Market cap"]
    assert not any("_" in name for names in groups.values() for name in names)


@pytest.mark.parametrize(
    ("failure", "shown"),
    [
        (RuntimeError("provider failed"), PUBLIC_FAILURE_MESSAGE),
        (ConfigurationError("SEC_USER_AGENT is not set"), "SEC_USER_AGENT is not set"),
    ],
)
def test_failed_turn_streams_a_public_error_and_keeps_prior_turns(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    shown: str,
) -> None:
    thread_id = _new_thread(client)
    before = _ask(client, thread_id, GUIDED_STORIES[0][1])

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise failure

    monkeypatch.setattr(api, "run_conversation_turn", fail)
    kind, data = _events(_post_turn(client, thread_id, "add Apple"))[-1]

    assert (kind, data) == ("error", {"message": shown})
    after = client.get(f"/api/threads/{thread_id}").json()
    assert after["turns"] == before["turns"]


def test_failed_turn_still_counts_against_the_thread_budget(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    monkeypatch.setattr(
        api,
        "runtime_for",
        lambda _kind, *, settings, budget: SimpleNamespace(budget=budget),
    )

    def spend_then_fail(_thread_id: str, _message: str, runtime: Any, **_: Any) -> None:
        runtime.budget.consume_live_sec()
        raise RuntimeError("provider failed")

    monkeypatch.setattr(api, "run_conversation_turn", spend_then_fail)
    assert _events(_post_turn(client, thread_id, "add Apple"))[-1][0] == "error"

    saved = LocalThreadStore(tmp_path / "threads").load(thread_id)
    assert saved is not None
    assert saved.turn_count == 2
    assert saved.live_sec_requests == 1
    assert [message.content for message in saved.messages] == [GUIDED_STORIES[0][1]]


def test_thread_survives_an_api_restart(tmp_path: Path) -> None:
    root = tmp_path / "threads"
    first = TestClient(create_app(_settings(), store_root=root))
    thread_id = _new_thread(first)
    _ask(first, thread_id, GUIDED_STORIES[1][1])
    view = _ask(first, thread_id, "add Apple")

    restarted = TestClient(create_app(_settings(), store_root=root))

    assert restarted.get(f"/api/threads/{thread_id}").json() == view


def test_expired_thread_reloads_empty_and_is_purged(client: TestClient, tmp_path: Path) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    store = LocalThreadStore(tmp_path / "threads")
    state = store.load(thread_id)
    assert state is not None
    store.save(state.model_copy(update={"updated_at": datetime(2020, 1, 1, tzinfo=UTC)}))

    view = client.get(f"/api/threads/{thread_id}").json()

    assert view["turns"] == []
    assert view["turn_count"] == 0
    assert store.load(thread_id) is None


def test_blank_message_is_rejected(client: TestClient) -> None:
    thread_id = _new_thread(client)
    assert _post_turn(client, thread_id, "   ").status_code == 422


@pytest.fixture
def runtimes_built(monkeypatch: pytest.MonkeyPatch) -> list[RuntimeKind]:
    """Record the runtime each turn asks for; serve recorded providers so tests stay offline."""
    built: list[RuntimeKind] = []

    def fake_runtime_for(kind: RuntimeKind, *, settings: Settings, **_: Any) -> Runtime:
        built.append(kind)
        return replace(recorded_runtime(), kind=resolve_runtime_kind(kind, settings))

    monkeypatch.setattr(api, "runtime_for", fake_runtime_for)
    return built


def test_thread_is_created_on_the_runtime_asked_for(
    client: TestClient, runtimes_built: list[RuntimeKind]
) -> None:
    recorded = client.post("/api/threads", json={"runtime": "recorded"}).json()
    live = client.post("/api/threads", json={"runtime": "live"}).json()

    assert recorded["runtime"] == "recorded"
    assert live["runtime"] == "live"
    assert recorded["notice"] is None and live["notice"] is None
    assert client.get(f"/api/threads/{recorded['thread_id']}").json()["runtime"] == "recorded"
    assert client.get(f"/api/threads/{live['thread_id']}").json()["runtime"] == "live"


def test_thread_without_a_runtime_takes_the_deployment_default(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(app_mode=AppMode.LIVE), store_root=tmp_path))
    assert client.post("/api/threads").json()["runtime"] == "live"


def test_turns_follow_the_thread_runtime(
    client: TestClient, runtimes_built: list[RuntimeKind]
) -> None:
    live = _new_thread(client, "live")
    recorded = _new_thread(client, "recorded")

    _ask(client, live, GUIDED_STORIES[0][1])
    _ask(client, recorded, GUIDED_STORIES[0][1])
    view = _ask(client, live, "add Apple")

    assert runtimes_built == [RuntimeKind.LIVE, RuntimeKind.RECORDED, RuntimeKind.LIVE]
    assert view["runtime"] == "live"
    assert len(view["turns"]) == 2


def test_locked_public_demo_creates_live_request_as_recorded(tmp_path: Path) -> None:
    client = TestClient(
        create_app(_settings(app_mode=AppMode.LIVE, public_demo=True), store_root=tmp_path)
    )
    created = client.post("/api/threads", json={"runtime": "live"}).json()

    assert created["runtime"] == "recorded"
    assert created["notice"] == "Live runtime is off on the public demo"
    view = _ask(client, created["thread_id"], GUIDED_STORIES[0][1])
    assert view["runtime"] == "recorded"


def test_turn_on_a_thread_bound_to_the_other_runtime_streams_a_public_error(
    tmp_path: Path, runtimes_built: list[RuntimeKind]
) -> None:
    open_demo = TestClient(create_app(_settings(), store_root=tmp_path))
    thread_id = _new_thread(open_demo, "live")
    locked_demo = TestClient(
        create_app(_settings(app_mode=AppMode.LIVE, public_demo=True), store_root=tmp_path)
    )

    events = _events(_post_turn(locked_demo, thread_id, GUIDED_STORIES[0][1]))

    kind, data = events[-1]
    assert kind == "error"
    assert data["message"] == (
        "This thread runs on the live runtime and cannot take a recorded turn. "
        "Start over to switch runtime."
    )
    view = locked_demo.get(f"/api/threads/{thread_id}").json()
    assert view["turns"] == []
    assert view["turn_count"] == 0
    assert view["runtime"] == "live"


def test_turn_request_no_longer_carries_a_runtime_flag(client: TestClient) -> None:
    thread_id = _new_thread(client)
    response = client.post(
        f"/api/threads/{thread_id}/turns", json={"message": "hi", "recorded": False}
    )
    assert response.status_code == 422


# --- Only the window's proxy may call the API (ADR 0006, ticket 03) ---

PROXY_TOKEN = "s3cret-proxy-token"
PROXY_HEADER = "X-Proxy-Token"  # web/lib/proxy.ts sends this name


@pytest.fixture
def guarded(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(_settings(api_proxy_token=PROXY_TOKEN), store_root=tmp_path / "threads")
    )


@pytest.mark.parametrize("header", [None, "", "wrong-token", PROXY_TOKEN + "x"])
def test_token_set_refuses_requests_without_the_matching_header(
    guarded: TestClient, header: str | None
) -> None:
    headers = {} if header is None else {PROXY_HEADER: header}
    for method, path, body in (
        ("GET", "/api/meta", None),
        ("POST", "/api/threads", {}),
        ("GET", f"/api/threads/{'0' * 8}-0000-0000-0000-{'0' * 12}", None),
        ("POST", f"/api/threads/{'0' * 8}-0000-0000-0000-{'0' * 12}/turns", {"message": "hi"}),
        ("DELETE", f"/api/threads/{'0' * 8}-0000-0000-0000-{'0' * 12}", None),
        ("GET", "/api/openapi.json", None),
    ):
        response = guarded.request(method, path, json=body, headers=headers)
        assert response.status_code == 401, (method, path)
        assert response.json() == {"detail": "Not authorized."}
        assert PROXY_TOKEN not in response.text


def test_token_set_serves_requests_with_the_matching_header(guarded: TestClient) -> None:
    guarded.headers[PROXY_HEADER] = PROXY_TOKEN
    assert guarded.get("/api/meta").status_code == 200
    thread_id = _new_thread(guarded)
    data = _ask(guarded, thread_id, GUIDED_STORIES[0][1])
    assert data["turns"][0]["presentation"]["fact_card"] is not None


def test_health_check_answers_with_or_without_the_token(guarded: TestClient) -> None:
    assert guarded.get("/api/health").json() == {"status": "ok"}
    assert guarded.get("/api/health", headers={PROXY_HEADER: "wrong"}).status_code == 200


def test_token_unset_needs_no_header(client: TestClient) -> None:
    assert client.get("/api/meta").status_code == 200
    assert client.get("/api/meta", headers={PROXY_HEADER: "anything"}).status_code == 200
    _ask(client, _new_thread(client), GUIDED_STORIES[0][1])


def test_token_comparison_is_constant_time(
    guarded: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    compared: list[tuple[bytes, bytes]] = []
    real = api.hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        compared.append((a, b))
        return real(a, b)

    monkeypatch.setattr(api.hmac, "compare_digest", spy)
    guarded.get("/api/meta", headers={PROXY_HEADER: "wrong"})
    assert compared == [(b"wrong", PROXY_TOKEN.encode())]


def test_public_demo_without_a_token_warns_at_startup(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="financial_analyst_agent")
    create_app(_settings(public_demo=True), store_root=tmp_path)
    assert any("API_PROXY_TOKEN" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "overrides", [{"public_demo": False}, {"public_demo": True, "api_proxy_token": "t"}]
)
def test_no_startup_warning_locally_or_with_a_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, overrides: dict[str, Any]
) -> None:
    caplog.set_level(logging.WARNING, logger="financial_analyst_agent")
    create_app(_settings(**overrides), store_root=tmp_path)
    assert not any("API_PROXY_TOKEN" in record.getMessage() for record in caplog.records)


def test_proxy_token_is_not_shown_in_settings_repr() -> None:
    assert PROXY_TOKEN not in repr(_settings(api_proxy_token=PROXY_TOKEN))
