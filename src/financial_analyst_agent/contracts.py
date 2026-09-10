"""Stable application contracts: ports, Runtime, result models, enums, metric constants.

Workflow implementations live in ``turn``; a graph package can import this module
without loading those workflows.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.domain.serialization import DecimalStr


class Intent(StrEnum):
    LOOKUP = "lookup"
    COMPARE = "compare"
    RANK = "rank"
    RANK_AND_LOOKUP = "rank_and_lookup"
    EXPLAIN = "explain"
    NEWS_AND_EXPLAIN = "news_and_explain"
    EXPLORATORY_RESEARCH = "exploratory_research"
    FILING_CHANGE = "filing_change"


class RendererKind(StrEnum):
    TABLE = "table"
    ESSAY = "essay"
    REFUSE = "refuse"
    CLARIFY = "clarify"


REPORTED_METRICS: tuple[str, ...] = (
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_expenses",
    "operating_income",
    "net_income",
    "research_and_development",
    "selling_general_and_administrative",
    "interest_expense",
    "income_tax_expense",
    "pretax_income",
)
FORMULA_METRICS: tuple[str, ...] = (
    "gross_margin",
    "operating_margin",
    "net_margin",
    "rd_to_sales",
    "sga_ratio",
    "effective_tax_rate",
    "interest_coverage",
)
SNAPSHOT_METRICS: tuple[str, ...] = ("market_cap",)
ALLOWED_METRICS: tuple[str, ...] = REPORTED_METRICS + FORMULA_METRICS + SNAPSHOT_METRICS
PERCENT_FORMULAS: tuple[str, ...] = (
    "gross_margin",
    "operating_margin",
    "net_margin",
    "rd_to_sales",
    "sga_ratio",
    "effective_tax_rate",
)
FORMULA_COMPONENTS: dict[str, tuple[str, str]] = {
    "gross_margin": ("gross_profit", "revenue"),
    "operating_margin": ("operating_income", "revenue"),
    "net_margin": ("net_income", "revenue"),
    "rd_to_sales": ("research_and_development", "revenue"),
    "sga_ratio": ("selling_general_and_administrative", "revenue"),
    "effective_tax_rate": ("income_tax_expense", "pretax_income"),
    "interest_coverage": ("operating_income", "interest_expense"),
}

PERIOD_MISMATCH = "period_mismatch"
MISSING_FACT = "missing_fact"
AMBIGUOUS_CONCEPT = "ambiguous_concept"
ZERO_DENOMINATOR = "zero_denominator"
MODEL_ANALYSIS_BANNER = "model-analysis"
EXPLORATORY_RESEARCH_BANNER = "exploratory-research"
SEARCH_NEWS_TOPIC = "news"
SEARCH_NEWS_MAX_RESULTS = 5
SEARCH_NEWS_TIME_RANGE = "week"


class Completer(Protocol):
    def complete(self, query: str, current_spec: Any | None = None) -> Any: ...


class EssayCompleter(Protocol):
    def complete_essay(self, query: str, tool_json: str = "") -> str: ...


class FactsPort(Protocol):
    def get_financials(
        self,
        company: str,
        metric: str,
        *,
        report_date: date | None = None,
    ) -> FinancialFact: ...


class RankingPort(Protocol):
    def rank_companies(self, industry: str, limit: int) -> Any: ...

    def lookup_member(self, company: str) -> Any: ...

    def snapshot_as_of(self) -> str: ...

    def snapshot_source(self) -> str: ...


class NewsPort(Protocol):
    def search_news(self, query: str) -> list["NewsHit"]: ...


@dataclass(frozen=True)
class Runtime:
    completer: Completer
    facts: FactsPort
    ranking: RankingPort | None = None
    news: NewsPort | None = None
    essay: EssayCompleter | None = None


class NewsHit(BaseModel):
    title: str
    url: str
    snippet: str = ""
    score: float | None = None
    published: str | None = None


class ToolTrace(BaseModel):
    tool: str
    args: dict[str, Any]
    provenance: dict[str, Any] = Field(default_factory=dict)


class ComponentProvenance(BaseModel):
    metric: str
    value: DecimalStr
    start_date: date
    end_date: date
    form: str
    accession_number: str
    taxonomy: str
    concept: str
    source_url: str
    source: str


class TableRow(BaseModel):
    company_name: str
    ticker: str
    cik: str
    metric: str
    rank: int | None = None
    value: DecimalStr | None = None
    currency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    form: str | None = None
    accession_number: str | None = None
    taxonomy: str | None = None
    concept: str | None = None
    source_url: str | None = None
    components: list[ComponentProvenance] = Field(default_factory=list)
    reason: str | None = None
    comparison: Literal["sequential", "yoy"] | None = None


class DisclosureChange(BaseModel):
    """Deterministic paragraph-level change between two accession-pinned sections."""

    section: Literal["mda", "risk_factors"]
    section_label: str
    change_kind: Literal["added", "removed", "changed"]
    before_text: str = ""
    after_text: str = ""
    older_accession: str
    newer_accession: str
    older_url: str
    newer_url: str
    selection_rule: str = (
        "Reviewed section extracted by Item heading; paragraph diff is deterministic."
    )


class TurnResult(BaseModel):
    intent: Intent
    tool_traces: list[ToolTrace]
    renderer: RendererKind
    table_rows: list[TableRow] = Field(default_factory=list)
    banners: list[str] = Field(default_factory=list)
    numeral_lock_extras: list[str] = Field(default_factory=list)
    message: str | None = None
    essay: str | None = None
    citations: list[NewsHit] = Field(default_factory=list)
    candidates: tuple[str, ...] = ()
    disclosure_changes: list[DisclosureChange] = Field(default_factory=list)
