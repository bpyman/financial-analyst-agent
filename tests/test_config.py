"""Settings load live credentials from the environment / .env file."""

import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ConfigurationError


def test_settings_loads_fmp_api_key_and_sec_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test-fmp-key")
    monkeypatch.setenv("SEC_USER_AGENT", "FinancialAnalystAgent (dev@example.com)")
    monkeypatch.setenv("FMP_BASE_URL", "https://fmp.example")

    settings = Settings()

    assert settings.require_fmp_api_key() == "test-fmp-key"
    assert settings.require_user_agent() == "FinancialAnalystAgent (dev@example.com)"
    assert settings.fmp_base_url == "https://fmp.example"


def test_settings_require_fmp_api_key_points_at_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "")

    with pytest.raises(ConfigurationError, match=r"FMP_API_KEY.*\.env"):
        Settings().require_fmp_api_key()


def test_settings_require_tavily_api_key_points_at_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "")

    with pytest.raises(ConfigurationError, match=r"TAVILY_API_KEY.*\.env"):
        Settings().require_tavily_api_key()
