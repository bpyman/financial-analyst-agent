"""Application seam: run_turn(query, runtime) → TurnResult.

Contracts (ports, Runtime, result models, enums, metric constants) live in
``contracts``; this module keeps the workflow implementations and re-exports
every public name callers already import from here.

``run_turn`` is a compatibility wrapper over an ephemeral conversation thread.
New multi-turn behaviour is asserted at ``run_conversation_turn``.
"""

import json
import re
from datetime import date
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    AMBIGUOUS_CONCEPT,
    EXPLORATORY_RESEARCH_BANNER,
    FORMULA_COMPONENTS,
    FORMULA_METRICS,
    MISSING_FACT,
    MODEL_ANALYSIS_BANNER,
    PERCENT_FORMULAS,
    PERIOD_MISMATCH,
    REPORTED_METRICS,
    SEARCH_NEWS_MAX_RESULTS,
    SEARCH_NEWS_TIME_RANGE,
    SEARCH_NEWS_TOPIC,
    SNAPSHOT_METRICS,
    ZERO_DENOMINATOR,
    Completer,
    ComponentProvenance,
    DisclosureChange,
    EssayCompleter,
    FactsPort,
    Intent,
    NewsHit,
    NewsPort,
    RankingPort,
    RendererKind,
    Runtime,
    TableRow,
    ToolTrace,
    TurnResult,
)
from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    AmbiguousFactError,
    CompanyNotFoundError,
    ProviderError,
    UnknownIndustryError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.observability import call_provider
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase

_LOOKUP_FAILURES = (
    AmbiguousFactError,
    UnsupportedQuarterlyFactError,
    AmbiguousCompanyError,
    CompanyNotFoundError,
)
_NUMERIC_TOKEN = re.compile(
    r"\$?\d[\d,]*(?:\.\d+)?(?:\s*(?:[KMBTkmbt]|[Bb]illion|[Mm]illion|[Tt]rillion))?"
)
_CITE_MARKER = re.compile(r"\[([1-9]\d*)\]")

__all__ = [
    "ALLOWED_METRICS",
    "AMBIGUOUS_CONCEPT",
    "EXPLORATORY_RESEARCH_BANNER",
    "FORMULA_COMPONENTS",
    "FORMULA_METRICS",
    "MISSING_FACT",
    "MODEL_ANALYSIS_BANNER",
    "PERCENT_FORMULAS",
    "PERIOD_MISMATCH",
    "REPORTED_METRICS",
    "SEARCH_NEWS_MAX_RESULTS",
    "SEARCH_NEWS_TIME_RANGE",
    "SEARCH_NEWS_TOPIC",
    "SNAPSHOT_METRICS",
    "ZERO_DENOMINATOR",
    "Completer",
    "ComponentProvenance",
    "DisclosureChange",
    "EssayCompleter",
    "FactsPort",
    "Intent",
    "NewsHit",
    "NewsPort",
    "RankingPort",
    "RendererKind",
    "Runtime",
    "TableRow",
    "ToolTrace",
    "TurnResult",
    "compare_metrics",
    "execute_turn",
    "run_turn",
    "snapshot_compare_rows",
]

def _strip_valid_citation_markers(essay: str, hit_count: int) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        index = int(raw)
        if raw == str(index) and 1 <= index <= hit_count:
            return ""
        return match.group(0)

    return _CITE_MARKER.sub(replace, essay)


def _numeral_lock_extras(essay: str, tool_json: str, *, hit_count: int = 0) -> list[str]:
    scanned = _strip_valid_citation_markers(essay, hit_count)
    allowed = set(_NUMERIC_TOKEN.findall(tool_json))
    return list(
        dict.fromkeys(token for token in _NUMERIC_TOKEN.findall(scanned) if token not in allowed)
    )


def _explain_turn(
    plan: Any, runtime: Runtime, *, grounding_json: str = ""
) -> TurnResult:
    if runtime.essay is None:
        raise RuntimeError("explain intent requires an essay completer")
    essay_completer = runtime.essay
    traces = [ToolTrace(tool="explain_topic", args={"topic": plan.topic})]
    try:
        essay = call_provider(
            "llm",
            lambda: essay_completer.complete_essay(plan.topic, grounding_json),
        )
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
    lock_json = grounding_json or json.dumps(
        [trace.model_dump(mode="json") for trace in traces]
    )
    extras = _numeral_lock_extras(essay, lock_json)
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
    news = runtime.news
    essay_completer = runtime.essay
    search_args = _search_news_args(query)
    try:
        hits = _usable_news_hits(call_provider("news", lambda: news.search_news(query)))
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
    essay = call_provider(
        "llm", lambda: essay_completer.complete_essay(query, tool_json)
    )
    extras = _numeral_lock_extras(essay, tool_json, hit_count=len(hits))
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


def _exploratory_research_turn(query: str, runtime: Runtime) -> TurnResult:
    """Cited research draft via the constrained news wrapper; never structured rows."""
    if runtime.news is None:
        raise RuntimeError("exploratory_research intent requires a news adapter")
    if runtime.essay is None:
        raise RuntimeError("exploratory_research intent requires an essay completer")
    news = runtime.news
    essay_completer = runtime.essay
    search_args = _search_news_args(query)
    try:
        hits = _usable_news_hits(call_provider("news", lambda: news.search_news(query)))
    except ProviderError as exc:
        return TurnResult(
            intent=Intent.EXPLORATORY_RESEARCH,
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
            intent=Intent.EXPLORATORY_RESEARCH,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message="No usable news hits for this query. Refusing rather than using training data.",
        )
    tool_json = _hits_json(hits)
    essay = call_provider(
        "llm", lambda: essay_completer.complete_essay(query, tool_json)
    )
    extras = _numeral_lock_extras(essay, tool_json, hit_count=len(hits))
    if extras:
        invented = ", ".join(extras)
        return TurnResult(
            intent=Intent.EXPLORATORY_RESEARCH,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            citations=hits,
            numeral_lock_extras=extras,
            message=f"Essay invented numeric tokens that were not in tool JSON: {invented}",
        )
    return TurnResult(
        intent=Intent.EXPLORATORY_RESEARCH,
        tool_traces=traces,
        renderer=RendererKind.ESSAY,
        banners=[EXPLORATORY_RESEARCH_BANNER],
        citations=hits,
        essay=essay,
        table_rows=[],
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


def _fact_source_kind(fact: Any) -> str:
    source = getattr(fact, "source", None)
    return str(source) if source else "sec_xbrl"


def _lookup_provenance(fact: Any) -> dict[str, Any]:
    return {
        "form": fact.form,
        "accession_number": fact.accession_number,
        "taxonomy": fact.taxonomy,
        "concept": fact.concept,
        "start_date": fact.start_date.isoformat(),
        "end_date": fact.end_date.isoformat(),
        "source": _fact_source_kind(fact),
        "source_url": fact.source_url,
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
        source=_fact_source_kind(fact),
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


def compare_metrics(
    facts: FactsPort,
    issuers: list[str],
    metric: str,
    *,
    report_date: date | None = None,
) -> list[TableRow]:
    """Resolve issuers, fetch formula components, and period-align Decimal results."""
    component_names = _component_metrics(metric)
    rows: list[TableRow] = []
    seen_ciks: set[str] = set()
    for issuer in issuers:
        try:
            if report_date is None:
                fetched = [
                    facts.get_financials(issuer, component) for component in component_names
                ]
            else:
                fetched = [
                    facts.get_financials(issuer, component, report_date=report_date)
                    for component in component_names
                ]
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


def _with_rank_identity(row: TableRow, company: Any, index: int) -> TableRow:
    return row.model_copy(
        update={
            "company_name": company.name,
            "ticker": company.ticker,
            "cik": company.cik,
            "rank": index,
        }
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
        if metric in SNAPSHOT_METRICS:
            rows.append(_snapshot_row(company, metric, rank=index))
            continue
        if metric in FORMULA_COMPONENTS:
            partial = _metrics_turn(Intent.RANK_AND_LOOKUP, [company.cik], metric, runtime)
            rows.append(_with_rank_identity(partial.table_rows[0], company, index))
            traces.extend(partial.tool_traces)
            continue
        args = {"company": company.cik, "metric": metric}
        try:
            fact = runtime.facts.get_financials(company.cik, metric)
        except _LOOKUP_FAILURES as exc:
            rows.append(_rank_and_lookup_row(company, index, metric, _partial_lookup_reason(exc)))
            traces.append(ToolTrace(tool="get_financials", args=args))
            continue
        rows.append(_with_rank_identity(_table_row_from_fact(fact), company, index))
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


def _compare_components_provenance(rows: list[TableRow]) -> dict[str, Any]:
    return {
        "components": [
            {"cik": row.cik, **component.model_dump(mode="json")}
            for row in rows
            for component in row.components
        ]
    }


def _metrics_turn(
    intent: Intent,
    issuers: list[str],
    metric: str,
    runtime: Runtime,
    *,
    report_date: date | None = None,
) -> TurnResult:
    if metric in SNAPSHOT_METRICS:
        return _snapshot_metrics_turn(intent, issuers, metric, runtime)
    rows = compare_metrics(runtime.facts, issuers, metric, report_date=report_date)
    args: dict[str, Any] = {"issuers": issuers, "metric": metric}
    if report_date is not None:
        args["report_date"] = report_date.isoformat()
    return TurnResult(
        intent=intent,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args=args,
                provenance=_compare_components_provenance(rows),
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=rows,
    )


def _snapshot_row(member: Any, metric: str, **kwargs: Any) -> TableRow:
    return TableRow(
        company_name=member.name,
        ticker=member.ticker,
        cik=member.cik,
        metric=metric,
        value=getattr(member, metric),
        currency="USD",
        **kwargs,
    )


def snapshot_compare_rows(
    ranking: RankingPort, issuers: list[str], metric: str
) -> list[TableRow]:
    rows: list[TableRow] = []
    seen_ciks: set[str] = set()
    for issuer in issuers:
        try:
            member = ranking.lookup_member(issuer)
        except (CompanyNotFoundError, AmbiguousCompanyError):
            rows.append(_compare_unresolved_row(issuer, metric, MISSING_FACT))
            continue
        if member.cik in seen_ciks:
            continue
        seen_ciks.add(member.cik)
        rows.append(_snapshot_row(member, metric))
    return rows


def _snapshot_metrics_turn(
    intent: Intent, issuers: list[str], metric: str, runtime: Runtime
) -> TurnResult:
    if runtime.ranking is None:
        raise RuntimeError(f"{intent.value} snapshot metric requires a ranking adapter")
    if intent is Intent.LOOKUP and len(issuers) == 1:
        try:
            member = runtime.ranking.lookup_member(issuers[0])
        except (CompanyNotFoundError, AmbiguousCompanyError) as exc:
            return TurnResult(
                intent=intent,
                tool_traces=[],
                renderer=RendererKind.REFUSE,
                message=str(exc),
            )
        rows = [_snapshot_row(member, metric)]
    else:
        rows = snapshot_compare_rows(runtime.ranking, issuers, metric)
    as_of = runtime.ranking.snapshot_as_of()
    return TurnResult(
        intent=intent,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={"issuers": issuers, "metric": metric},
                provenance={
                    "snapshot_as_of": as_of,
                    "source": runtime.ranking.snapshot_source(),
                },
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=rows,
        banners=[f"Universe snapshot as of {as_of}"],
    )


def _compare_turn(plan: Any, runtime: Runtime) -> TurnResult:
    report_date = getattr(plan, "report_date", None)
    return _metrics_turn(
        Intent.COMPARE, list(plan.companies), plan.metric, runtime, report_date=report_date
    )


def _lookup_turn(plan: Any, runtime: Runtime) -> TurnResult:
    metric = plan.metric
    report_date = getattr(plan, "report_date", None)
    if metric in FORMULA_COMPONENTS:
        return _metrics_turn(
            Intent.LOOKUP, [plan.company], metric, runtime, report_date=report_date
        )
    if metric in SNAPSHOT_METRICS:
        return _snapshot_metrics_turn(Intent.LOOKUP, [plan.company], metric, runtime)
    args: dict[str, Any] = {"company": plan.company, "metric": metric}
    if report_date is not None:
        args["report_date"] = report_date.isoformat()
    try:
        if report_date is None:
            fact = runtime.facts.get_financials(plan.company, metric)
        else:
            fact = runtime.facts.get_financials(
                plan.company, metric, report_date=report_date
            )
    except _LOOKUP_FAILURES as exc:
        return TurnResult(
            intent=Intent.LOOKUP,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    return TurnResult(
        intent=Intent.LOOKUP,
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


def _run_workflow(plan: Any, runtime: Runtime, *, query: str = "") -> TurnResult:
    from financial_analyst_agent.graph import run_workflow_turn

    return run_workflow_turn(plan, runtime, query=query)


def execute_turn(query: str, runtime: Runtime) -> TurnResult:
    """Plan and run one one-shot analysis. Run state is not returned or persisted."""
    plan = runtime.completer.complete(query)
    if plan.intent is Intent.EXPLAIN:
        return _run_workflow(plan, runtime, query=query)
    if plan.intent is Intent.FILING_CHANGE:
        return _run_workflow(plan, runtime, query=query)
    if plan.intent is Intent.NEWS_AND_EXPLAIN:
        return _run_workflow(plan, runtime, query=query)
    if plan.intent is Intent.EXPLORATORY_RESEARCH:
        return _run_workflow(plan, runtime, query=query)
    if plan.intent is Intent.RANK:
        return _run_workflow(plan, runtime, query=query)
    resolved = resolve_metric_phrase(query)
    if resolved.kind == "ambiguous":
        return _clarify_metric(plan.intent, resolved.candidates)
    if resolved.kind == "unknown":
        fallback = plan.metric if isinstance(plan.metric, str) else "unknown"
        term = fallback if fallback not in ALLOWED_METRICS else "unknown"
        return _refuse_unknown_metric(plan.intent, term)
    if resolved.kind == "unique" and len(resolved.metrics) > 1:
        # One-shot execute_turn still clarifies; multi-metric composition runs
        # through run_spec_turn on the conversation seam (ticket 09).
        return _clarify_metric(plan.intent, resolved.metrics)
    if resolved.kind == "unique" and resolved.metric is not None:
        metric = resolved.metric
    else:
        metric = str(plan.metric or "")
    plan = _plan_with_metric(plan, metric)
    if plan.intent is Intent.COMPARE:
        if metric not in ALLOWED_METRICS:
            return _refuse_unknown_metric(plan.intent, metric)
        return _run_workflow(plan, runtime, query=query)
    if plan.intent is Intent.RANK_AND_LOOKUP:
        if metric not in ALLOWED_METRICS:
            return _refuse_unknown_metric(plan.intent, metric)
        return _run_workflow(plan, runtime, query=query)
    if plan.intent is Intent.LOOKUP:
        if metric not in ALLOWED_METRICS:
            return _refuse_unknown_metric(plan.intent, metric)
        return _run_workflow(plan, runtime, query=query)
    raise ValueError(f"unsupported intent: {plan.intent!r}")


def run_turn(query: str, runtime: Runtime) -> TurnResult:
    """Compatibility wrapper: one ephemeral conversation thread → TurnResult."""
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    return run_conversation_turn(
        "ephemeral",
        query,
        runtime,
        store=EphemeralThreadStore(),
    ).result
