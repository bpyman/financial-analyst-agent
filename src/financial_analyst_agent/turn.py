"""Application seam: run_turn(query, runtime) → TurnResult."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    AmbiguousFactError,
    CompanyNotFoundError,
    UnknownIndustryError,
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
FORMULA_COMPONENTS: dict[str, tuple[str, str]] = {
    "gross_margin": ("gross_profit", "revenue"),
    "operating_margin": ("operating_income", "revenue"),
    "net_margin": ("net_income", "revenue"),
}

_LOOKUP_FAILURES = (
    UnsupportedQuarterlyFactError,
    AmbiguousFactError,
    AmbiguousCompanyError,
    CompanyNotFoundError,
)
PERIOD_MISMATCH = "period_mismatch"
MISSING_FACT = "missing_fact"
AMBIGUOUS_CONCEPT = "ambiguous_concept"


class Completer(Protocol):
    def complete(self, query: str) -> Any: ...


class FactsPort(Protocol):
    def get_financials(self, company: str, metric: str) -> Any: ...


class RankingPort(Protocol):
    def rank_companies(self, industry: str, limit: int) -> Any: ...


@dataclass(frozen=True)
class Runtime:
    completer: Completer
    facts: FactsPort
    ranking: RankingPort | None = None


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


class TurnResult(BaseModel):
    intent: Intent
    tool_traces: list[ToolTrace]
    renderer: RendererKind
    table_rows: list[TableRow] = Field(default_factory=list)
    banners: list[str] = Field(default_factory=list)
    numeral_lock_extras: list[str] = Field(default_factory=list)
    message: str | None = None


def _lookup_facts(result: Any) -> list[Any]:
    facts = list(result) if isinstance(result, (list, tuple)) else [result]
    return facts


def _table_row_from_fact(fact: Any) -> TableRow:
    metric = fact.metric
    metric_value = metric.value if hasattr(metric, "value") else metric
    return TableRow(
        company_name=fact.company_name,
        ticker=fact.ticker,
        cik=fact.cik,
        metric=metric_value,
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


def _lookup_provenance(facts: list[Any]) -> dict[str, Any]:
    primary = facts[0]
    provenance: dict[str, Any] = {
        "accession_number": primary.accession_number,
        "concept": primary.concept,
        "source_url": primary.source_url,
        "start_date": primary.start_date.isoformat(),
        "end_date": primary.end_date.isoformat(),
    }
    if len(facts) > 1:
        provenance["concepts"] = [fact.concept for fact in facts]
    return provenance


def _refuse_unknown_metric(intent: Intent, metric: str) -> TurnResult:
    allowed = ", ".join(ALLOWED_METRICS)
    return TurnResult(
        intent=intent,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=f"Unknown metric {metric!r}. Allowed: {allowed}",
    )


def _rank_turn(plan: Any, runtime: Runtime) -> TurnResult:
    if runtime.ranking is None:
        raise RuntimeError("rank intent requires a ranking adapter")
    try:
        table = runtime.ranking.rank_companies(plan.industry, plan.limit)
    except UnknownIndustryError as exc:
        return TurnResult(
            intent=Intent.RANK,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    rows = [
        TableRow(
            company_name=company.name,
            ticker=company.ticker,
            cik=company.cik,
            metric="market_cap",
            rank=index,
            value=company.market_cap,
            currency="USD",
        )
        for index, company in enumerate(table.companies, start=1)
    ]
    return TurnResult(
        intent=Intent.RANK,
        tool_traces=[
            ToolTrace(
                tool="rank_companies",
                args={"industry": plan.industry, "limit": plan.limit},
                provenance={
                    "snapshot_as_of": table.as_of,
                    "source": table.source,
                    "sector": table.sector,
                },
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=rows,
        banners=[f"Universe snapshot as of {table.as_of}"],
    )


def _component_metrics(metric: str) -> tuple[str, ...]:
    formula = FORMULA_COMPONENTS.get(metric)
    if formula is not None:
        return formula
    return (metric,)


def _provenance_from_fact(fact: Any, metric: str) -> ComponentProvenance:
    return ComponentProvenance(
        metric=metric,
        value=fact.value,
        start_date=fact.start_date,
        end_date=fact.end_date,
        form=fact.form,
        accession_number=fact.accession_number,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        source_url=fact.source_url,
    )


def _formula_value(metric: str, facts: list[Any]) -> Any:
    components = FORMULA_COMPONENTS.get(metric)
    if components is None:
        return facts[0].value
    numerator, denominator = facts
    return numerator.value / denominator.value


def _aligned_period(facts: list[Any]) -> tuple[date, date] | None:
    periods = {(fact.start_date, fact.end_date) for fact in facts}
    if len(periods) != 1:
        return None
    return next(iter(periods))


def compare_metrics(facts: FactsPort, issuers: list[str], metric: str) -> list[TableRow]:
    """Resolve issuers, fetch formula components, and period-align Decimal results."""
    component_names = _component_metrics(metric)
    rows: list[TableRow] = []
    seen_ciks: set[str] = set()
    for issuer in issuers:
        try:
            fetched_groups = [
                _lookup_facts(facts.get_financials(issuer, component))
                for component in component_names
            ]
        except _LOOKUP_FAILURES:
            rows.append(
                TableRow(
                    company_name=issuer,
                    ticker="",
                    cik="",
                    metric=metric,
                    reason=MISSING_FACT,
                )
            )
            continue
        if any(len(group) != 1 for group in fetched_groups):
            identity = fetched_groups[0][0]
            if identity.cik in seen_ciks:
                continue
            seen_ciks.add(identity.cik)
            rows.append(
                TableRow(
                    company_name=identity.company_name,
                    ticker=identity.ticker,
                    cik=identity.cik,
                    metric=metric,
                    reason=AMBIGUOUS_CONCEPT,
                )
            )
            continue
        fetched = [group[0] for group in fetched_groups]
        identity = fetched[0]
        if identity.cik in seen_ciks:
            continue
        seen_ciks.add(identity.cik)
        period = _aligned_period(fetched)
        components = [
            _provenance_from_fact(fact, component)
            for fact, component in zip(fetched, component_names, strict=True)
        ]
        if period is None:
            rows.append(
                TableRow(
                    company_name=identity.company_name,
                    ticker=identity.ticker,
                    cik=identity.cik,
                    metric=metric,
                    components=components,
                    reason=PERIOD_MISMATCH,
                )
            )
            continue
        period_start, period_end = period
        rows.append(
            TableRow(
                company_name=identity.company_name,
                ticker=identity.ticker,
                cik=identity.cik,
                metric=metric,
                value=_formula_value(metric, fetched),
                start_date=period_start,
                end_date=period_end,
                components=components,
            )
        )
    comparable_periods = {
        (row.start_date, row.end_date) for row in rows if row.value is not None
    }
    if len(comparable_periods) > 1:
        rows = [
            row.model_copy(update={"value": None, "reason": PERIOD_MISMATCH})
            if row.value is not None
            else row
            for row in rows
        ]
    return rows


def _rank_and_lookup_row(company: Any, index: int, metric: str, reason: str) -> TableRow:
    return TableRow(
        company_name=company.name,
        ticker=company.ticker,
        cik=company.cik,
        metric=metric,
        rank=index,
        reason=reason,
    )


def _rank_and_lookup_turn(plan: Any, runtime: Runtime) -> TurnResult:
    if runtime.ranking is None:
        raise RuntimeError("rank_and_lookup intent requires a ranking adapter")
    metric = plan.metric
    try:
        table = runtime.ranking.rank_companies(plan.industry, plan.limit)
    except UnknownIndustryError as exc:
        return TurnResult(
            intent=Intent.RANK_AND_LOOKUP,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    traces = [
        ToolTrace(
            tool="rank_companies",
            args={"industry": plan.industry, "limit": plan.limit},
            provenance={
                "snapshot_as_of": table.as_of,
                "source": table.source,
                "sector": table.sector,
            },
        )
    ]
    rows: list[TableRow] = []
    for index, company in enumerate(table.companies, start=1):
        args = {"company": company.cik, "metric": metric}
        try:
            fetched = runtime.facts.get_financials(company.cik, metric)
            facts = _lookup_facts(fetched)
        except _LOOKUP_FAILURES:
            rows.append(_rank_and_lookup_row(company, index, metric, MISSING_FACT))
            traces.append(ToolTrace(tool="get_financials", args=args))
            continue
        if len(facts) != 1:
            rows.append(_rank_and_lookup_row(company, index, metric, AMBIGUOUS_CONCEPT))
            traces.append(ToolTrace(tool="get_financials", args=args))
            continue
        fact = facts[0]
        rows.append(
            _table_row_from_fact(fact).model_copy(
                update={
                    "company_name": company.name,
                    "ticker": company.ticker,
                    "cik": company.cik,
                    "rank": index,
                }
            )
        )
        traces.append(
            ToolTrace(
                tool="get_financials",
                args=args,
                provenance=_lookup_provenance(facts),
            )
        )
    return TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        tool_traces=traces,
        renderer=RendererKind.TABLE,
        table_rows=rows,
        banners=[f"Universe snapshot as of {table.as_of}"],
    )


def _compare_turn(plan: Any, runtime: Runtime) -> TurnResult:
    issuers = list(plan.companies)
    metric = plan.metric
    rows = compare_metrics(runtime.facts, issuers, metric)
    return TurnResult(
        intent=Intent.COMPARE,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={"issuers": issuers, "metric": metric},
                provenance={
                    "components": [
                        {
                            "cik": row.cik,
                            "metric": component.metric,
                            "accession_number": component.accession_number,
                            "concept": component.concept,
                            "start_date": component.start_date.isoformat(),
                            "end_date": component.end_date.isoformat(),
                            "source_url": component.source_url,
                        }
                        for row in rows
                        for component in row.components
                    ]
                },
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=rows,
    )


def run_turn(query: str, runtime: Runtime) -> TurnResult:
    plan = runtime.completer.complete(query)
    if plan.intent is Intent.COMPARE:
        if plan.metric not in ALLOWED_METRICS:
            return _refuse_unknown_metric(plan.intent, plan.metric)
        return _compare_turn(plan, runtime)
    if plan.intent is Intent.RANK:
        return _rank_turn(plan, runtime)
    if plan.intent is Intent.RANK_AND_LOOKUP:
        if plan.metric not in REPORTED_METRICS:
            return _refuse_unknown_metric(plan.intent, plan.metric)
        return _rank_and_lookup_turn(plan, runtime)
    if plan.intent is Intent.LOOKUP and plan.metric not in REPORTED_METRICS:
        return _refuse_unknown_metric(plan.intent, plan.metric)
    args = {"company": plan.company, "metric": plan.metric}
    try:
        fetched = runtime.facts.get_financials(plan.company, plan.metric)
    except _LOOKUP_FAILURES as exc:
        return TurnResult(
            intent=plan.intent,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    facts = _lookup_facts(fetched)
    if len(facts) != 1:
        return TurnResult(
            intent=plan.intent,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message="Supported concepts produced conflicting quarterly values",
        )
    fact = facts[0]
    return TurnResult(
        intent=plan.intent,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args=args,
                provenance=_lookup_provenance(facts),
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=[_table_row_from_fact(fact)],
    )
