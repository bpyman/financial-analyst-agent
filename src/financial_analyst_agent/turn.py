"""Application seam: run_turn(query, runtime) → TurnResult."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.errors import (
    AmbiguousFactError,
    CompanyNotFoundError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.serialization import DecimalStr


class Intent(StrEnum):
    LOOKUP = "lookup"
    COMPARE = "compare"
    RANK = "rank"
    RANK_AND_LOOKUP = "rank_and_lookup"
    EXPLAIN = "explain"
    NEWS_AND_EXPLAIN = "news_and_explain"


class RendererKind(StrEnum):
    TABLE = "table"
    ESSAY = "essay"
    REFUSE = "refuse"


REPORTED_METRICS: tuple[str, ...] = (
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_expenses",
    "operating_income",
    "net_income",
)
FORMULA_METRICS: tuple[str, ...] = (
    "gross_margin",
    "operating_margin",
    "net_margin",
)
ALLOWED_METRICS: tuple[str, ...] = REPORTED_METRICS + FORMULA_METRICS

_LOOKUP_FAILURES = (
    UnsupportedQuarterlyFactError,
    AmbiguousFactError,
    CompanyNotFoundError,
)


class Completer(Protocol):
    def complete(self, query: str) -> Any: ...


class FactsPort(Protocol):
    def get_financials(self, company: str, metric: str) -> Any: ...


@dataclass(frozen=True)
class Runtime:
    completer: Completer
    facts: FactsPort


class ToolTrace(BaseModel):
    tool: str
    args: dict[str, str]
    provenance: dict[str, str] = Field(default_factory=dict)


class TableRow(BaseModel):
    company_name: str
    ticker: str
    cik: str
    metric: str
    value: DecimalStr
    currency: str
    start_date: date
    end_date: date
    form: str
    accession_number: str
    taxonomy: str
    concept: str
    source_url: str


class TurnResult(BaseModel):
    intent: Intent
    tool_traces: list[ToolTrace]
    renderer: RendererKind
    table_rows: list[TableRow] = Field(default_factory=list)
    banners: list[str] = Field(default_factory=list)
    numeral_lock_extras: list[str] = Field(default_factory=list)
    message: str | None = None


def run_turn(query: str, runtime: Runtime) -> TurnResult:
    plan = runtime.completer.complete(query)
    if plan.intent is Intent.LOOKUP and plan.metric not in REPORTED_METRICS:
        allowed = ", ".join(ALLOWED_METRICS)
        return TurnResult(
            intent=plan.intent,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message=f"Unknown metric {plan.metric!r}. Allowed: {allowed}",
        )
    args = {"company": plan.company, "metric": plan.metric}
    try:
        fact = runtime.facts.get_financials(plan.company, plan.metric)
    except _LOOKUP_FAILURES as exc:
        return TurnResult(
            intent=plan.intent,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    return TurnResult(
        intent=plan.intent,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args=args,
                provenance={
                    "accession_number": fact.accession_number,
                    "concept": fact.concept,
                    "source_url": fact.source_url,
                    "start_date": fact.start_date.isoformat(),
                    "end_date": fact.end_date.isoformat(),
                },
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=[
            TableRow(
                company_name=fact.company_name,
                ticker=fact.ticker,
                cik=fact.cik,
                metric=fact.metric,
                value=fact.value,
                currency=fact.currency,
                start_date=fact.start_date,
                end_date=fact.end_date,
                form=fact.form,
                accession_number=fact.accession_number,
                taxonomy=fact.taxonomy,
                concept=fact.concept,
                source_url=fact.source_url,
            )
        ],
    )
