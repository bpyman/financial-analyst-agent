"""OpenAI structured-output planner. Default suite uses a fake parse client."""

from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.planner import OpenAIStructuredCompleter, Plan
from financial_analyst_agent.runtime import DemoCompleter, fixture_runtime, live_runtime
from financial_analyst_agent.turn import Intent, run_turn
from test_run_turn_lookup import GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY

_MODEL = "gpt-4o-2024-11-20"
_CLOSED_INTENTS = {intent.value for intent in Intent}


class _FakeParseClient:
    def __init__(self, parsed: object) -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self.parse))
        self._parsed = parsed

    def parse(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        message = SimpleNamespace(parsed=self._parsed, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def test_openai_completer_emits_closed_intent_from_structured_output() -> None:
    parsed = Plan(intent=Intent.LOOKUP, company="Google", metric="net_income")
    client = _FakeParseClient(parsed)
    completer = OpenAIStructuredCompleter(client, _MODEL)

    plan = completer.complete(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY)

    assert plan.intent is Intent.LOOKUP
    assert plan.intent.value in _CLOSED_INTENTS
    assert plan.company == "Google"
    assert plan.metric == "net_income"
    assert client.calls[0]["model"] == _MODEL
    assert client.calls[0]["response_format"] is Plan
    contents = [item["content"] for item in client.calls[0]["messages"]]
    assert GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY in contents


def test_openai_completer_schema_only_allows_closed_intents() -> None:
    schema = Plan.model_json_schema()
    names = set(schema["$defs"]["Intent"]["enum"])
    assert names == _CLOSED_INTENTS


def test_missing_openai_config_is_configuration_error_not_regex_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", "")
    with pytest.raises(ConfigurationError, match=r"OPENAI"):
        live_runtime(Settings())


def test_live_runtime_uses_openai_completer_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", _MODEL)
    monkeypatch.setenv("SEC_USER_AGENT", "FinancialAnalystAgent (dev@example.com)")
    runtime = live_runtime(Settings())
    assert isinstance(runtime.completer, OpenAIStructuredCompleter)
    assert not isinstance(runtime.completer, DemoCompleter)


def test_fixture_runtime_still_uses_injected_fake_completer() -> None:
    runtime = fixture_runtime()
    assert isinstance(runtime.completer, DemoCompleter)
    result = run_turn(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, runtime)
    assert result.intent is Intent.LOOKUP
