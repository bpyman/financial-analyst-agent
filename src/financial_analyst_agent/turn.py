"""Application seam: run_turn(query, runtime) → TurnResult."""

import json
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import SimpleNamespace
from typing import Any, Protocol

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    AmbiguousFactError,
    CompanyNotFoundError,
    ProviderError,
    UnknownIndustryError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.domain.serialization import DecimalStr
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase


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
    CLARIFY = "clarify"


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
    AmbiguousFactError,
    UnsupportedQuarterlyFactError,
    AmbiguousCompanyError,
    CompanyNotFoundError,
)
PERIOD_MISMATCH = "period_mismatch"
MISSING_FACT = "missing_fact"
AMBIGUOUS_CONCEPT = "ambiguous_concept"
ZERO_DENOMINATOR = "zero_denominator"
MODEL_ANALYSIS_BANNER = "model-analysis"
SEARCH_NEWS_TOPIC = "news"
SEARCH_NEWS_MAX_RESULTS = 5
SEARCH_NEWS_TIME_RANGE = "week"
_NUMERIC_TOKEN = re.compile(
    r"\$?\d[\d,]*(?:\.\d+)?(?:\s*(?:[KMBTkmbt]|[Bb]illion|[Mm]illion|[Tt]rillion))?"
)


class Completer(Protocol):
    def complete(self, query: str) -> Any: ...


class EssayCompleter(Protocol):
    def complete_essay(self, query: str, tool_json: str = "") -> str: ...


class FactsPort(Protocol):
    def get_financials(self, company: str, metric: str) -> FinancialFact: ...


class RankingPort(Protocol):
    def rank_companies(self, industry: str, limit: int) -> Any: ...


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
    essay: str | None = None
    citations: list[NewsHit] = Field(default_factory=list)
    candidates: tuple[str, ...] = ()


def _numeral_lock_extras(essay: str, tool_json: str) -> list[str]:
    allowed = set(_NUMERIC_TOKEN.findall(tool_json))
    return list(
        dict.fromkeys(token for token in _NUMERIC_TOKEN.findall(essay) if token not in allowed)
    )


def _explain_turn(plan: Any, runtime: Runtime) -> TurnResult:
    if runtime.essay is None:
        raise RuntimeError("explain intent requires an essay completer")
    traces = [ToolTrace(tool="explain_topic", args={"topic": plan.topic})]
    try:
        essay = runtime.essay.complete_essay(plan.topic)
    except ProviderError as exc:
        traces[0] = traces[0].model_copy(
            update={"provenance": {"error": {"code": exc.code, "message": str(exc)}}}
        )
        return TurnResult(
            intent=Intent.EXPLAIN,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    extras = _numeral_lock_extras(
        essay, json.dumps([trace.model_dump(mode="json") for trace in traces])
    )
    if extras:
        invented = ", ".join(extras)
        return TurnResult(
            intent=Intent.EXPLAIN,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            numeral_lock_extras=extras,
            message=f"Essay invented numeric tokens that were not in tool JSON: {invented}",
        )
    return TurnResult(
        intent=Intent.EXPLAIN,
        tool_traces=traces,
        renderer=RendererKind.ESSAY,
        banners=[MODEL_ANALYSIS_BANNER],
        essay=essay,
    )


def _usable_news_hits(hits: list[NewsHit]) -> list[NewsHit]:
    usable = [hit for hit in hits if hit.title.strip() and hit.url.strip()]
    return usable[:SEARCH_NEWS_MAX_RESULTS]


def _search_news_args(query: str) -> dict[str, Any]:
    return {
        "query": query,
        "topic": SEARCH_NEWS_TOPIC,
        "max_results": SEARCH_NEWS_MAX_RESULTS,
        "time_range": SEARCH_NEWS_TIME_RANGE,
    }


def _hits_json(hits: list[NewsHit]) -> str:
    return json.dumps([hit.model_dump(mode="json") for hit in hits])


def _news_and_explain_turn(query: str, runtime: Runtime) -> TurnResult:
    if runtime.news is None:
        raise RuntimeError("news_and_explain intent requires a news adapter")
    if runtime.essay is None:
        raise RuntimeError("news_and_explain intent requires an essay completer")
    search_args = _search_news_args(query)
    try:
        hits = _usable_news_hits(runtime.news.search_news(query))
    except ProviderError as exc:
        return TurnResult(
            intent=Intent.NEWS_AND_EXPLAIN,
            tool_traces=[
                ToolTrace(
                    tool="search_news",
                    args=search_args,
                    provenance={
                        "error": {"code": exc.code, "message": str(exc)},
                    },
                )
            ],
            renderer=RendererKind.REFUSE,
            message=("News search is unavailable. Refusing rather than using training data."),
        )
    traces = [
        ToolTrace(
            tool="search_news",
            args=search_args,
            provenance={"hits": [hit.model_dump(mode="json") for hit in hits]},
        )
    ]
    if not hits:
        return TurnResult(
            intent=Intent.NEWS_AND_EXPLAIN,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message="No usable news hits for this query. Refusing rather than using training data.",
        )
    tool_json = _hits_json(hits)
    essay = runtime.essay.complete_essay(query, tool_json)
    extras = _numeral_lock_extras(essay, tool_json)
    if extras:
        invented = ", ".join(extras)
        return TurnResult(
            intent=Intent.NEWS_AND_EXPLAIN,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            citations=hits,
            numeral_lock_extras=extras,
            message=f"Essay invented numeric tokens that were not in tool JSON: {invented}",
        )
    return TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        tool_traces=traces,
        renderer=RendererKind.ESSAY,
        citations=hits,
        essay=essay,
    )


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


def _lookup_provenance(fact: Any) -> dict[str, Any]:
    return {
        "accession_number": fact.accession_number,
        "concept": fact.concept,
        "source_url": fact.source_url,
        "start_date": fact.start_date.isoformat(),
        "end_date": fact.end_date.isoformat(),
    }


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
    industry = plan.industry or ""
    try:
        table = runtime.ranking.rank_companies(industry, plan.limit)
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
                args={"industry": industry, "limit": plan.limit},
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


def _partial_lookup_reason(exc: BaseException) -> str:
    return AMBIGUOUS_CONCEPT if isinstance(exc, AmbiguousFactError) else MISSING_FACT


def _compare_unresolved_row(issuer: str, metric: str, reason: str) -> TableRow:
    return TableRow(
        company_name=issuer,
        ticker="",
        cik="",
        metric=metric,
        reason=reason,
    )


def _compare_row(identity: Any, metric: str, **kwargs: Any) -> TableRow:
    return TableRow(
        company_name=identity.company_name,
        ticker=identity.ticker,
        cik=identity.cik,
        metric=metric,
        **kwargs,
    )


def compare_metrics(facts: FactsPort, issuers: list[str], metric: str) -> list[TableRow]:
    """Resolve issuers, fetch formula components, and period-align Decimal results."""
    component_names = _component_metrics(metric)
    rows: list[TableRow] = []
    seen_ciks: set[str] = set()
    for issuer in issuers:
        try:
            fetched = [facts.get_financials(issuer, component) for component in component_names]
        except _LOOKUP_FAILURES as exc:
            rows.append(_compare_unresolved_row(issuer, metric, _partial_lookup_reason(exc)))
            continue
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
                _compare_row(
                    identity,
                    metric,
                    components=components,
                    reason=PERIOD_MISMATCH,
                )
            )
            continue
        period_start, period_end = period
        if metric in FORMULA_COMPONENTS:
            _numerator, denominator = fetched
            if denominator.value == 0:
                rows.append(
                    _compare_row(
                        identity,
                        metric,
                        start_date=period_start,
                        end_date=period_end,
                        components=components,
                        reason=ZERO_DENOMINATOR,
                    )
                )
                continue
        rows.append(
            _compare_row(
                identity,
                metric,
                value=_formula_value(metric, fetched),
                start_date=period_start,
                end_date=period_end,
                components=components,
            )
        )
    comparable_periods = {(row.start_date, row.end_date) for row in rows if row.value is not None}
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
    industry = plan.industry or ""
    try:
        table = runtime.ranking.rank_companies(industry, plan.limit)
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
            args={"industry": industry, "limit": plan.limit},
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
            fact = runtime.facts.get_financials(company.cik, metric)
        except _LOOKUP_FAILURES as exc:
            rows.append(_rank_and_lookup_row(company, index, metric, _partial_lookup_reason(exc)))
            traces.append(ToolTrace(tool="get_financials", args=args))
            continue
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
                provenance=_lookup_provenance(fact),
            )
        )
    return TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        tool_traces=traces,
        renderer=RendererKind.TABLE,
        table_rows=rows,
        banners=[f"Universe snapshot as of {table.as_of}"],
    )


def _metrics_turn(intent: Intent, issuers: list[str], metric: str, runtime: Runtime) -> TurnResult:
    rows = compare_metrics(runtime.facts, issuers, metric)
    return TurnResult(
        intent=intent,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={"issuers": issuers, "metric": metric},
                provenance={
                    "components": [
                        {
                            "cik": row.cik,
                            "metric": component.metric,
                            "value": str(component.value),
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


def _compare_turn(plan: Any, runtime: Runtime) -> TurnResult:
    return _metrics_turn(Intent.COMPARE, list(plan.companies), plan.metric, runtime)


def _plan_with_metric(plan: Any, metric: str) -> Any:
    return SimpleNamespace(
        intent=plan.intent,
        company=getattr(plan, "company", None),
        companies=list(getattr(plan, "companies", []) or []),
        metric=metric,
        industry=getattr(plan, "industry", None),
        limit=getattr(plan, "limit", 10),
        topic=getattr(plan, "topic", None),
    )


def _clarify_metric(intent: Intent, candidates: tuple[str, ...]) -> TurnResult:
    return TurnResult(
        intent=intent,
        tool_traces=[],
        renderer=RendererKind.CLARIFY,
        candidates=candidates,
    )


def run_turn(query: str, runtime: Runtime) -> TurnResult:
    plan = runtime.completer.complete(query)
    if plan.intent is Intent.EXPLAIN:
        return _explain_turn(plan, runtime)
    if plan.intent is Intent.NEWS_AND_EXPLAIN:
        return _news_and_explain_turn(query, runtime)
    if plan.intent is Intent.RANK:
        return _rank_turn(plan, runtime)
    resolved = resolve_metric_phrase(query)
    if resolved.kind == "ambiguous":
        return _clarify_metric(plan.intent, resolved.candidates)
    if resolved.kind == "unknown":
        fallback = plan.metric if isinstance(plan.metric, str) else "unknown"
        term = fallback if fallback not in ALLOWED_METRICS else "unknown"
        return _refuse_unknown_metric(plan.intent, term)
    if resolved.kind == "unique" and resolved.metric is not None:
        metric = resolved.metric
    else:
        metric = str(plan.metric or "")
    plan = _plan_with_metric(plan, metric)
    if plan.intent is Intent.COMPARE:
        if metric not in ALLOWED_METRICS:
            return _refuse_unknown_metric(plan.intent, metric)
        return _compare_turn(plan, runtime)
    if plan.intent is Intent.RANK_AND_LOOKUP:
        if metric not in REPORTED_METRICS:
            return _refuse_unknown_metric(plan.intent, metric)
        return _rank_and_lookup_turn(plan, runtime)
    if plan.intent is Intent.LOOKUP:
        if metric not in ALLOWED_METRICS:
            return _refuse_unknown_metric(plan.intent, metric)
        if metric in FORMULA_COMPONENTS:
            return _metrics_turn(Intent.LOOKUP, [plan.company], metric, runtime)
    args = {"company": plan.company, "metric": metric}
    try:
        fact = runtime.facts.get_financials(plan.company, metric)
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
                provenance=_lookup_provenance(fact),
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=[_table_row_from_fact(fact)],
    )
