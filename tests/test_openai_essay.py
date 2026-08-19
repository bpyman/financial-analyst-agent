"""OpenAI-backed essay completion for the live runtime."""

from types import SimpleNamespace
from typing import Any

import openai
import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.essay import OpenAIEssayCompleter
from financial_analyst_agent.runtime import live_runtime

_MODEL = "gpt-4o-2024-11-20"
_MINING_QUERY = "How can AI disrupt mining?"
_MINING_ESSAY = "AI can improve ore sorting and predictive maintenance in mining."
_NEWS_QUERY = "What is going on with NVIDIA's supply chain?"
_NEWS_TOOL_JSON = (
    '[{"title":"NVIDIA flags packaging constraints",'
    '"url":"https://example.test/nvidia","snippet":"CoWoS lead times remain extended."}]'
)


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=_MINING_ESSAY)


def test_live_runtime_generates_explain_essay_with_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeOpenAIClient()
    monkeypatch.setattr(openai, "OpenAI", lambda **_kwargs: client)
    runtime = live_runtime(
        Settings(
            openai_api_key="sk-test",
            openai_model=_MODEL,
            sec_user_agent="FinancialAnalystAgent (dev@example.com)",
            tavily_api_key="tvly-test",
        )
    )

    assert runtime.essay is not None
    essay = runtime.essay.complete_essay(_MINING_QUERY)

    assert essay == _MINING_ESSAY
    assert len(client.calls) == 1
    assert client.calls[0]["model"] == _MODEL
    assert _MINING_QUERY in client.calls[0]["input"]


def test_openai_news_essay_receives_query_and_tool_json() -> None:
    client = _FakeOpenAIClient()
    completer = OpenAIEssayCompleter(client, _MODEL)

    completer.complete_essay(_NEWS_QUERY, _NEWS_TOOL_JSON)

    prompt = client.calls[0]["input"]
    assert _NEWS_QUERY in prompt
    assert _NEWS_TOOL_JSON in prompt
    instructions = client.calls[0]["instructions"].casefold()
    assert "only" in instructions
    assert "news tool json" in instructions
