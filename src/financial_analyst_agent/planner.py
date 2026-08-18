"""OpenAI structured-output planner. Emits a closed intent, never numbers."""

from typing import Any

import openai
from pydantic import BaseModel, Field

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import PlannerError
from financial_analyst_agent.turn import ALLOWED_METRICS, Intent

_PLANNER_FAILED_MESSAGE = "LLM planner failed"
_SYSTEM_PROMPT = (
    "Map the user question to a Plan. "
    "intent must be one of lookup, compare, rank, rank_and_lookup, explain, "
    "news_and_explain. "
    "Use lookup for a named company's latest quarterly reported metric. "
    "Use compare for two or more issuers on a reported metric or margin formula. "
    "Use rank for top-N industry market-cap ranking without a reported metric. "
    "Use rank_and_lookup when the user wants top-N and a reported metric for each. "
    "Use explain for qualitative industry or AI-disruption questions with no retrieval. "
    "Use news_and_explain for named-company current events (supply chain, what's going on). "
    f"Allowed metrics: {', '.join(ALLOWED_METRICS)}. "
    "For explain, set topic to the user question. "
    "Never calculate, select, or invent financial values."
)


class Plan(BaseModel):
    intent: Intent
    company: str | None = None
    companies: list[str] = Field(default_factory=list)
    metric: str | None = None
    industry: str | None = None
    limit: int = 10
    topic: str | None = None


class OpenAIStructuredCompleter:
    """Calls OpenAI parse() with Plan as the constrained response schema."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIStructuredCompleter":
        api_key = settings.require_openai_api_key()
        model = settings.require_openai_model()
        base_url = settings.openai_base_url.strip() or None
        return cls(openai.OpenAI(api_key=api_key, base_url=base_url), model)

    def complete(self, query: str) -> Plan:
        try:
            completion = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                response_format=Plan,
            )
        except openai.OpenAIError as exc:
            raise PlannerError(
                _PLANNER_FAILED_MESSAGE,
                details={"stage": "http", "error_class": type(exc).__name__},
            ) from exc
        try:
            choice = completion.choices[0]
            message = choice.message
        except (AttributeError, IndexError, TypeError) as exc:
            raise PlannerError(
                _PLANNER_FAILED_MESSAGE,
                details={"stage": "malformed", "error_class": type(exc).__name__},
            ) from exc
        if getattr(message, "refusal", None):
            raise PlannerError(_PLANNER_FAILED_MESSAGE, details={"stage": "refusal"})
        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise PlannerError(_PLANNER_FAILED_MESSAGE, details={"stage": "missing_parsed"})
        if isinstance(parsed, Plan):
            return parsed
        return Plan.model_validate(parsed)
