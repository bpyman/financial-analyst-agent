"""Application configuration."""

import math
import re
from enum import StrEnum
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from financial_analyst_agent.domain.errors import ConfigurationError

_USER_AGENT_EMAIL_PATTERN = re.compile(
    r"^(.+?)\s+\(([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\)\s*$"
)


class AppMode(StrEnum):
    LIVE = "live"
    FIXTURE = "fixture"


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
    app_mode: AppMode = AppMode.LIVE

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

    def require_user_agent(self) -> str:
        if not self.sec_user_agent.strip():
            raise ConfigurationError(
                "SEC_USER_AGENT is required for live SEC access. "
                "Set SEC_USER_AGENT in the environment or .env file."
            )
        return self.sec_user_agent


def get_settings() -> Settings:
    return Settings()
