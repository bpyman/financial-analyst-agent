"""OpenAI structured-output planner. Emits a closed intent or a spec patch."""

from typing import Annotated, Any, Literal

import openai
from pydantic import AfterValidator, BaseModel, model_validator

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import PlannerError
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, PeriodSelection, SpecPatch
from financial_analyst_agent.turn import ALLOWED_METRICS, Intent

_PLANNER_FAILED_MESSAGE = "LLM planner failed"
_SYSTEM_PROMPT = (
    "Map the user question to a Plan. "
    "intent must be one of lookup, compare, rank, rank_and_lookup, explain, "
    "news_and_explain, exploratory_research, filing_change. "
    "Use lookup for a named company's latest quarterly reported metric. "
    "Use compare for two or more issuers on a reported metric or formula. "
    "Use rank for top-N industry market-cap ranking without a reported metric. "
    "Use rank_and_lookup when the user wants top-N and a reported metric "
    "or formula for each. "
    "Use explain for qualitative industry or AI-disruption questions with no retrieval. "
    "Use news_and_explain for named-company current events (supply chain, what's going on). "
    "Use exploratory_research for questions that no analysis spec expresses "
    "(themes, open research drafts) that need cited news evidence rather than "
    "structured financial rows. "
    "Use filing_change when the user asks what changed in MD&A or Risk Factors "
    "between two named 10-Q or 10-K accession numbers. Set company, older_accession, "
    "newer_accession, and section (mda, risk_factors, or both). "
    "Set summarize true only when they also ask for a summary. "
    f"Allowed metrics: {', '.join(ALLOWED_METRICS)}. "
    "For explain, set topic to the user question. "
    "For exploratory_research, set topic to the user question. "
    "Never calculate, select, or invent financial values."
)
_FOLLOW_UP_PROMPT = (
    "The analyst is continuing a conversation thread. The current analysis spec "
    "is provided. Map this follow-up to a FollowUpPlan. "
    "Use intent spec_patch when they are editing or replacing the quantitative "
    "analysis. mode=extend when they add/remove/swap companies or metrics, "
    "change the period window, or ask for year-over-year on the current analysis. "
    "mode=replace when they start an unrelated new analysis, including a "
    "complete lookup or compare question about different issuers. "
    "mode=null when extend versus replace is unclear. "
    "Company names as the user said them — never CIKs. "
    "Do not invent financial values. "
    "Use explain / news_and_explain / exploratory_research only for qualitative "
    "or current-event questions that are not a spec edit. "
    "Use filing_change for MD&A or Risk Factors comparison between two accessions. "
    f"Allowed metrics: {', '.join(ALLOWED_METRICS)}. "
    "Allowed operations: across_companies, across_periods, rank."
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


class _ExploratoryResearchPlan(BaseModel):
    intent: Literal[Intent.EXPLORATORY_RESEARCH]
    topic: NonEmptyText


class _FilingChangePlan(BaseModel):
    intent: Literal[Intent.FILING_CHANGE]
    company: NonEmptyText
    older_accession: NonEmptyText
    newer_accession: NonEmptyText
    section: NonEmptyText = "mda"
    summarize: bool = False


PlanAction = (
    _LookupPlan
    | _ComparePlan
    | _RankPlan
    | _RankAndLookupPlan
    | _ExplainPlan
    | _NewsAndExplainPlan
    | _ExploratoryResearchPlan
    | _FilingChangePlan
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
        if isinstance(self.action, (_ExplainPlan, _ExploratoryResearchPlan)):
            return self.action.topic
        return None


class _SpecPatchAction(BaseModel):
    intent: Literal["spec_patch"]
    mode: Literal["extend", "replace"] | None = None
    add_companies: tuple[str, ...] = ()
    remove_companies: tuple[str, ...] = ()
    add_metrics: tuple[str, ...] = ()
    remove_metrics: tuple[str, ...] = ()
    period_kind: Literal["latest_quarter", "last_n_quarters"] | None = None
    period_count: int | None = None
    add_operations: tuple[str, ...] = ()
    remove_operations: tuple[str, ...] = ()
    ranked_industry: str | None = None
    ranked_limit: PositiveLimit | None = None

    def to_spec_patch(self) -> SpecPatch:
        periods: PeriodSelection | None = None
        if self.period_kind == "last_n_quarters":
            periods = PeriodSelection(
                kind="last_n_quarters",
                count=self.period_count if self.period_count is not None else 4,
            )
        elif self.period_kind == "latest_quarter":
            periods = PeriodSelection()
        ranked = None
        if self.ranked_industry:
            ranked = (self.ranked_industry, int(self.ranked_limit or 10))
        return SpecPatch(
            mode=self.mode,
            add_companies=self.add_companies,
            remove_companies=self.remove_companies,
            add_metrics=self.add_metrics,
            remove_metrics=self.remove_metrics,
            set_periods=periods,
            add_operations=self.add_operations,
            remove_operations=self.remove_operations,
            ranked_request=ranked,
        )


FollowUpAction = (
    _SpecPatchAction
    | _ExplainPlan
    | _NewsAndExplainPlan
    | _ExploratoryResearchPlan
    | _FilingChangePlan
)


class FollowUpPlan(BaseModel):
    action: FollowUpAction

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_action(cls, value: Any) -> Any:
        if isinstance(value, dict) and "action" not in value and "intent" in value:
            return {"action": value}
        return value


def format_spec_for_planner(spec: AnalysisSpec) -> str:
    companies = ", ".join(
        f"{company.name} ({company.ticker})" for company in spec.companies
    ) or "(none)"
    constituents = "(none)"
    if spec.constituents is not None:
        constituents = f"{spec.constituents.industry} top {spec.constituents.limit}"
    metrics = ", ".join(spec.metrics) or "(none)"
    period_label: str = spec.periods.kind
    if spec.periods.count is not None:
        period_label = f"{spec.periods.kind} n={spec.periods.count}"
    operations = ", ".join(spec.operations) or "(none)"
    return (
        f"Companies: {companies}\n"
        f"Ranked constituents: {constituents}\n"
        f"Metrics: {metrics}\n"
        f"Periods: {period_label}\n"
        f"Operations: {operations}"
    )


def openai_client_from_settings(settings: Settings) -> tuple[Any, str]:
    api_key = settings.require_openai_api_key()
    model = settings.require_openai_model()
    base_url = settings.openai_base_url.strip() or None
    return openai.OpenAI(api_key=api_key, base_url=base_url), model


class OpenAIStructuredCompleter:
    """Calls OpenAI parse() with Plan as the constrained response schema."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIStructuredCompleter":
        return cls(*openai_client_from_settings(settings))

    def complete(self, query: str, current_spec: AnalysisSpec | None = None) -> Plan | SpecPatch:
        if current_spec is None:
            system = _SYSTEM_PROMPT
            response_format: type[BaseModel] = Plan
        else:
            system = (
                f"{_FOLLOW_UP_PROMPT}\n\nCurrent analysis spec:\n"
                f"{format_spec_for_planner(current_spec)}"
            )
            response_format = FollowUpPlan
        try:
            completion = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
                response_format=response_format,
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
        if isinstance(parsed, FollowUpPlan):
            if isinstance(parsed.action, _SpecPatchAction):
                return parsed.action.to_spec_patch()
            return Plan(action=parsed.action)
        if isinstance(parsed, Plan):
            return parsed
        if current_spec is None:
            return Plan.model_validate(parsed)
        follow = FollowUpPlan.model_validate(parsed)
        if isinstance(follow.action, _SpecPatchAction):
            return follow.action.to_spec_patch()
        return Plan(action=follow.action)
