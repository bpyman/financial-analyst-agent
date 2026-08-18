"""OpenAI structured-output planner. Emits a closed intent, never numbers."""

from typing import Annotated, Any, Literal

import openai
from pydantic import AfterValidator, BaseModel, model_validator

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


def _nonempty_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


def _at_least_two_companies(value: list[str]) -> list[str]:
    if len(value) < 2:
        raise ValueError("companies must contain at least two issuers")
    return value


def _positive_limit(value: int) -> int:
    if value < 1:
        raise ValueError("limit must be positive")
    return value


NonEmptyText = Annotated[str, AfterValidator(_nonempty_text)]
ComparedCompanies = Annotated[list[NonEmptyText], AfterValidator(_at_least_two_companies)]
PositiveLimit = Annotated[int, AfterValidator(_positive_limit)]


class _LookupPlan(BaseModel):
    intent: Literal[Intent.LOOKUP]
    company: NonEmptyText
    metric: NonEmptyText


class _ComparePlan(BaseModel):
    intent: Literal[Intent.COMPARE]
    companies: ComparedCompanies
    metric: NonEmptyText


class _RankPlan(BaseModel):
    intent: Literal[Intent.RANK]
    industry: NonEmptyText
    limit: PositiveLimit = 10


class _RankAndLookupPlan(BaseModel):
    intent: Literal[Intent.RANK_AND_LOOKUP]
    industry: NonEmptyText
    metric: NonEmptyText
    limit: PositiveLimit = 10


class _ExplainPlan(BaseModel):
    intent: Literal[Intent.EXPLAIN]
    topic: NonEmptyText


class _NewsAndExplainPlan(BaseModel):
    intent: Literal[Intent.NEWS_AND_EXPLAIN]


PlanAction = (
    _LookupPlan
    | _ComparePlan
    | _RankPlan
    | _RankAndLookupPlan
    | _ExplainPlan
    | _NewsAndExplainPlan
)


class Plan(BaseModel):
    action: PlanAction

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_action(cls, value: Any) -> Any:
        if isinstance(value, dict) and "action" not in value and "intent" in value:
            return {"action": value}
        return value

    @property
    def intent(self) -> Intent:
        return self.action.intent

    @property
    def company(self) -> str | None:
        if isinstance(self.action, _LookupPlan):
            return self.action.company
        return None

    @property
    def companies(self) -> list[str]:
        if isinstance(self.action, _ComparePlan):
            return self.action.companies
        return []

    @property
    def metric(self) -> str | None:
        if isinstance(self.action, (_LookupPlan, _ComparePlan, _RankAndLookupPlan)):
            return self.action.metric
        return None

    @property
    def industry(self) -> str | None:
        if isinstance(self.action, (_RankPlan, _RankAndLookupPlan)):
            return self.action.industry
        return None

    @property
    def limit(self) -> int:
        if isinstance(self.action, (_RankPlan, _RankAndLookupPlan)):
            return self.action.limit
        return 10

    @property
    def topic(self) -> str | None:
        if isinstance(self.action, _ExplainPlan):
            return self.action.topic
        return None


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
