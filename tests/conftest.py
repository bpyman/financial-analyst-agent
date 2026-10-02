"""Shared pytest helpers."""

from collections.abc import Iterator

import pytest

from financial_analyst_agent.providers.sec.client import SEC_PAUSE


@pytest.fixture(autouse=True)
def _keep_non_network_tests_offline(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prevent a developer .env from selecting live providers in ordinary tests."""
    if request.node.get_closest_marker("network"):
        return
    monkeypatch.setenv("APP_MODE", "recorded")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("SEC_USER_AGENT", "")
    monkeypatch.setenv("FMP_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")


@pytest.fixture(autouse=True)
def _sec_not_paused() -> Iterator[None]:
    """A Retry-After or block page in one test must not pause SEC for the next."""
    SEC_PAUSE.clear()
    yield
    SEC_PAUSE.clear()
