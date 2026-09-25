"""Application configuration."""

import logging
import math
import re
from enum import StrEnum
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from financial_analyst_agent.domain.errors import ConfigurationError

_USER_AGENT_EMAIL_PATTERN = re.compile(
    r"^(.+?)\s+\(([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\)\s*$"
)


_LOGGER = logging.getLogger("financial_analyst_agent")
_DEPRECATED_APP_MODES = {"fixture": "recorded"}


class AppMode(StrEnum):
    """Which runtime `APP_MODE` selects: the recorded runtime or the live runtime."""

    LIVE = "live"
    RECORDED = "recorded"

    @classmethod
    def _missing_(cls, value: object) -> "AppMode | None":
        if not isinstance(value, str):
            return None
        normalized = value.strip().casefold()
        replacement = _DEPRECATED_APP_MODES.get(normalized)
        if replacement is not None:
            _LOGGER.warning(
                "APP_MODE=%s is deprecated; use APP_MODE=%s", normalized, replacement
            )
            normalized = replacement
        for member in cls:
            if member.value == normalized:
                return member
        return None


def _reject_non_finite(value: float, field_name: str) -> float:
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{field_name} must be a finite number")
    return value


class Settings(BaseSettings):
    """Typed settings loaded from environment variables."""

    sec_user_agent: str = ""
    sec_base_url: str = "https://data.sec.gov"
    sec_max_requests_per_second: float = 5.0
    sec_timeout_seconds: float = 30.0
    sec_cache_dir: Path | None = None
    fmp_api_key: str = ""
    fmp_base_url: str = "https://financialmodelingprep.com"
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"
    openai_base_url: str = ""
    app_mode: AppMode = AppMode.LIVE
    public_demo: bool = False
    demo_live_sec: bool = False
    allow_public_openai: bool = False
    allow_public_tavily: bool = False
    api_proxy_token: SecretStr = SecretStr("")
    thread_ttl_seconds: int = 7200
    max_turns_per_thread: int = 25
    max_live_sec_requests_per_thread: int = 25
    snapshot_stale_after_days: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("sec_user_agent")
    @classmethod
    def validate_user_agent(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return stripped
        match = _USER_AGENT_EMAIL_PATTERN.match(stripped)
        if match is None:
            raise ValueError(
                "SEC_USER_AGENT must include a descriptive application name and "
                "contact email, e.g. 'FinancialAnalystAgent (you@example.com)'"
            )
        if not match.group(1).strip():
            raise ValueError("SEC_USER_AGENT application name must be nonempty")
        return stripped

    @field_validator("sec_max_requests_per_second")
    @classmethod
    def validate_max_requests_per_second(cls, value: float) -> float:
        value = _reject_non_finite(value, "SEC_MAX_REQUESTS_PER_SECOND")
        if value <= 0 or value > 5:
            raise ValueError("SEC_MAX_REQUESTS_PER_SECOND must be greater than 0 and at most 5")
        return value

    @field_validator("sec_timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, value: float) -> float:
        value = _reject_non_finite(value, "SEC_TIMEOUT_SECONDS")
        if value <= 0:
            raise ValueError("SEC_TIMEOUT_SECONDS must be greater than 0")
        return value

    @field_validator("fmp_base_url")
    @classmethod
    def validate_fmp_base_url(cls, value: str) -> str:
        stripped = value.strip().rstrip("/")
        if not stripped:
            raise ValueError("FMP_BASE_URL must be nonempty")
        return stripped

    @field_validator("tavily_base_url")
    @classmethod
    def validate_tavily_base_url(cls, value: str) -> str:
        stripped = value.strip().rstrip("/")
        if not stripped:
            raise ValueError("TAVILY_BASE_URL must be nonempty")
        return stripped

    def require_user_agent(self) -> str:
        if not self.sec_user_agent.strip():
            raise ConfigurationError(
                "SEC_USER_AGENT is required for live SEC access. "
                "Set SEC_USER_AGENT in the environment or .env file."
            )
        return self.sec_user_agent

    def require_fmp_api_key(self) -> str:
        key = self.fmp_api_key.strip()
        if not key:
            raise ConfigurationError(
                "FMP_API_KEY is required to rebuild the universe snapshot. "
                "Set FMP_API_KEY in the environment or .env file."
            )
        return key

    def require_tavily_api_key(self) -> str:
        key = self.tavily_api_key.strip()
        if not key:
            raise ConfigurationError(
                "TAVILY_API_KEY is required for live news search. "
                "Set TAVILY_API_KEY in the environment or .env file."
            )
        return key

    def require_openai_api_key(self) -> str:
        key = self.openai_api_key.strip()
        if not key:
            raise ConfigurationError(
                "OPENAI_API_KEY is required for the live planner. "
                "Set OPENAI_API_KEY in the environment or .env file."
            )
        return key

    def require_openai_model(self) -> str:
        model = self.openai_model.strip()
        if not model:
            raise ConfigurationError(
                "OPENAI_MODEL is required for the live planner. "
                "Set OPENAI_MODEL in the environment or .env file."
            )
        return model


def get_settings() -> Settings:
    return Settings()
