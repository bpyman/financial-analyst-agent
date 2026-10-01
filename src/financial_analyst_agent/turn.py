"""Application seam: run_turn(query, runtime) → TurnResult.

Contracts (ports, Runtime, result models, enums, metric constants) live in
``contracts``; this module keeps the workflow implementations and re-exports
every public name callers already import from here.

``run_turn`` is a compatibility wrapper over an ephemeral conversation thread.
New multi-turn behaviour is asserted at ``run_conversation_turn``.
"""

import json
import re
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    AMBIGUOUS_CONCEPT,
    DIFFERENCE_FORMULAS,
    EXPLORATORY_RESEARCH_BANNER,
    FORMULA_COMPONENTS,
    FORMULA_METRICS,
    INSTANT_METRICS,
    LATEST_PERIOD_ONLY,
    MARKET_FORMULAS,
    MISSING_FACT,
    MODEL_ANALYSIS_BANNER,
    NEWS_SUMMARY_BANNER,
    NOT_MEANINGFUL,
    NOT_REPORTED_FOR_QUARTER,
    PERCENT_FORMULAS,
    PERIOD_MISMATCH,
    REPORTED_METRICS,
    SEARCH_NEWS_MAX_RESULTS,
    SEARCH_NEWS_TIME_RANGE,
    SEARCH_NEWS_TOPIC,
    SNAPSHOT_METRICS,
    SUM_FORMULAS,
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
    RuntimeKind,
    TableRow,
    ToolTrace,
    TurnResult,
    refuse_unknown_metric,
    snapshot_banner,
)
from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    AmbiguousFactError,
    CompanyNotFoundError,
    PerShareNotDerivableError,
    ProviderError,
    UnknownIndustryError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.observability import call_provider
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
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
# Grounding keys whose digits identify a document rather than state a figure.
_IDENTIFIER_KEYS = frozenset({"url", "cik", "document", "primary_document", "anchor"})

__all__ = [
    "ALLOWED_METRICS",
    "AMBIGUOUS_CONCEPT",
    "EXPLORATORY_RESEARCH_BANNER",
    "NEWS_SUMMARY_BANNER",
    "FORMULA_COMPONENTS",
    "FORMULA_METRICS",
    "MARKET_FORMULAS",
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
    "RuntimeKind",
    "TableRow",
    "ToolTrace",
    "TurnResult",
    "compare_metrics",
    "execute_turn",
    "market_formula_rows",
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


def _is_identifier_key(key: str) -> bool:
    key = key.casefold()
    return key in _IDENTIFIER_KEYS or key.endswith("_url") or "accession" in key


def _grounding_text(tool_json: str) -> str:
    """The grounding's readable values, without the digits of links and identifiers.

    "0000950170-25-061046" and an article's URL are not figures an essay can
    quote: "25%" must not pass because an accession number holds "-25-".
    """
    try:
        payload = json.loads(tool_json)
    except ValueError:
        return tool_json
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if not _is_identifier_key(str(key)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif value is not None:
            parts.append(str(value))

    walk(payload)
    return "\n".join(parts)


def _numeral_lock_extras(essay: str, tool_json: str, *, hit_count: int = 0) -> list[str]:
    scanned = _strip_valid_citation_markers(essay, hit_count)
    allowed = set(_NUMERIC_TOKEN.findall(_grounding_text(tool_json)))
    return list(
        dict.fromkeys(token for token in _NUMERIC_TOKEN.findall(scanned) if token not in allowed)
    )


def _numeral_lock_message(invented: str) -> str:
    return (
        "The written answer was withheld because it quoted numbers its sources "
        f"do not contain: {invented}."
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
            message=_numeral_lock_message(invented),
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


NO_NEWS_MESSAGE = (
    "I found no news articles for this, and I only answer news questions from articles I "
    "can cite."
)


def _no_news_message(runtime: Runtime) -> str:
    if runtime.kind is not RuntimeKind.RECORDED:
        return NO_NEWS_MESSAGE
    from financial_analyst_agent.news import FIXTURE_NEWS_QUERY

    return (
        f"{NO_NEWS_MESSAGE} The recorded demo only replays captured news for "
        f"“{FIXTURE_NEWS_QUERY}”."
    )


def _news_grounded_essay_turn(
    query: str, runtime: Runtime, *, intent: Intent, banners: list[str] | None = None
) -> TurnResult:
    if runtime.news is None:
        raise RuntimeError(f"{intent.value} intent requires a news adapter")
    if runtime.essay is None:
        raise RuntimeError(f"{intent.value} intent requires an essay completer")
    news = runtime.news
    essay_completer = runtime.essay
    search_args = _search_news_args(query)
    try:
        hits = _usable_news_hits(call_provider("news", lambda: news.search_news(query)))
    except ProviderError as exc:
        return TurnResult(
            intent=intent,
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
            message=(
                "News search is unavailable right now, and I only answer news questions "
                "from articles I can cite."
            ),
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
            intent=intent,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=_no_news_message(runtime),
        )
    tool_json = _hits_json(hits)
    essay = call_provider(
        "llm", lambda: essay_completer.complete_essay(query, tool_json)
    )
    extras = _numeral_lock_extras(essay, tool_json, hit_count=len(hits))
    if extras:
        invented = ", ".join(extras)
        return TurnResult(
            intent=intent,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            citations=hits,
            numeral_lock_extras=extras,
            message=_numeral_lock_message(invented),
        )
    return TurnResult(
        intent=intent,
        tool_traces=traces,
        renderer=RendererKind.ESSAY,
        citations=hits,
        banners=list(banners) if banners else [],
        essay=essay,
    )


def _news_and_explain_turn(query: str, runtime: Runtime) -> TurnResult:
    return _news_grounded_essay_turn(
        query, runtime, intent=Intent.NEWS_AND_EXPLAIN, banners=[NEWS_SUMMARY_BANNER]
    )


def _exploratory_research_turn(query: str, runtime: Runtime) -> TurnResult:
    """Cited research draft via the constrained news wrapper; never structured rows."""
    return _news_grounded_essay_turn(
        query,
        runtime,
        intent=Intent.EXPLORATORY_RESEARCH,
        banners=[EXPLORATORY_RESEARCH_BANNER],
    )


def _derivation_fields(fact: FinancialFact) -> dict[str, Any]:
    """A derived quarter's label and the reported facts it came from (ADR 0007)."""
    derivation = getattr(fact, "derivation", None)
    if derivation is None:
        return {}
    metric = fact.metric.value if hasattr(fact.metric, "value") else str(fact.metric)
    source = _fact_source_kind(fact)

    def provenance(part: Any, parent: str = metric) -> ComponentProvenance:
        nested = getattr(part, "derivation", None)
        own = getattr(part, "metric", None) or parent
        return ComponentProvenance(
            metric=own,
            value=part.value,
            start_date=part.start_date,
            end_date=part.end_date,
            form=part.form,
            accession_number=part.accession_number,
            taxonomy=part.taxonomy,
            concept=part.concept,
            source_url=part.source_url,
            source=source,
            derivation=nested.label if nested is not None else None,
            derived_from=[provenance(inner, own) for inner in nested.parts] if nested else [],
        )

    return {
        "derivation": derivation.label,
        "derived_from": [provenance(part) for part in derivation.parts],
    }


def _table_row_from_fact(fact: FinancialFact) -> TableRow:
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
        newer_filing_end=getattr(fact, "newer_filing_end", None),
        **_derivation_fields(fact),
    )


def _fact_source_kind(fact: FinancialFact) -> str:
    source = getattr(fact, "source", None)
    return str(source) if source else "sec_xbrl"


def _lookup_provenance(fact: FinancialFact) -> dict[str, Any]:
    derivation = getattr(fact, "derivation", None)
    extra: dict[str, Any] = {}
    if derivation is not None:
        extra["derivation"] = derivation.model_dump(mode="json")
    return extra | {
        "form": fact.form,
        "accession_number": fact.accession_number,
        "taxonomy": fact.taxonomy,
        "concept": fact.concept,
        "start_date": fact.start_date.isoformat(),
        "end_date": fact.end_date.isoformat(),
        "source": _fact_source_kind(fact),
        "source_url": fact.source_url,
    }


def _ranked_table(
    plan: Any, runtime: Runtime, intent: Intent
) -> tuple[Any, ToolTrace] | TurnResult:
    """Rank the plan's industry, or a refusal when the industry is unknown."""
    if runtime.ranking is None:
        raise RuntimeError(f"{intent.value} intent requires a ranking adapter")
    industry = plan.industry or ""
    try:
        table = runtime.ranking.rank_companies(industry, plan.limit)
    except UnknownIndustryError as exc:
        return TurnResult(
            intent=intent,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    trace = ToolTrace(
        tool="rank_companies",
        args={"industry": industry, "limit": plan.limit},
        provenance={
            "snapshot_as_of": table.as_of,
            "source": table.source,
            "sector": table.sector,
        },
    )
    return table, trace


def _rank_turn(plan: Any, runtime: Runtime) -> TurnResult:
    ranked = _ranked_table(plan, runtime, Intent.RANK)
    if isinstance(ranked, TurnResult):
        return ranked
    table, trace = ranked
    rows = [
        _snapshot_row(company, "market_cap", rank=index)
        for index, company in enumerate(table.companies, start=1)
    ]
    return TurnResult(
        intent=Intent.RANK,
        tool_traces=[trace],
        renderer=RendererKind.TABLE,
        table_rows=rows,
        banners=[snapshot_banner(table.as_of)],
    )


def _component_metrics(metric: str) -> tuple[str, ...]:
    formula = FORMULA_COMPONENTS.get(metric)
    if formula is not None:
        return formula
    return (metric,)


def _provenance_from_fact(fact: FinancialFact, metric: str) -> ComponentProvenance:
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
        **_derivation_fields(fact),
    )


def _formula_value(metric: str, facts: list[FinancialFact]) -> Any:
    components = FORMULA_COMPONENTS.get(metric)
    if components is None:
        return facts[0].value
    first, second = facts
    if metric in DIFFERENCE_FORMULAS:
        return first.value - second.value
    if metric in SUM_FORMULAS:
        return first.value + second.value
    return first.value / second.value


def _metric_name(fact: FinancialFact) -> str:
    metric = fact.metric
    return metric.value if hasattr(metric, "value") else str(metric)


def _aligned_period(facts: list[FinancialFact]) -> tuple[date, date] | None:
    """The period every component covers; a balance-sheet amount needs only its date.

    Return on equity divides a trailing year by the equity on its last day, so
    the row keeps the year and the equity must be at that year's end.
    """
    durations = [fact for fact in facts if _metric_name(fact) not in INSTANT_METRICS]
    periods = {(fact.start_date, fact.end_date) for fact in durations or facts}
    if len(periods) != 1:
        return None
    period = next(iter(periods))
    if any(fact.end_date != period[1] for fact in facts):
        return None
    return period


PERIODS_DIFFER_BANNER = (
    "These companies' latest quarters end on different dates, so the values cover "
    "different periods. Each row shows its own quarter."
)


def _same_fiscal_period(periods: set[tuple[date | None, date | None]]) -> bool:
    """True when every period is one fiscal quarter, allowing 52/53-week calendars.

    Apple's quarter ending March 28 and Microsoft's ending March 31 are the same
    quarter; bounds further apart than ``FISCAL_WEEK_TOLERANCE`` are not.
    """
    if len(periods) <= 1:
        return True
    starts = [start for start, _end in periods if start is not None]
    ends = [end for _start, end in periods if end is not None]
    if len(starts) != len(periods) or len(ends) != len(periods):
        return False
    return all(
        max(bounds) - min(bounds) <= FISCAL_WEEK_TOLERANCE for bounds in (starts, ends)
    )


def _partial_lookup_reason(exc: BaseException) -> str:
    if isinstance(exc, PerShareNotDerivableError):
        return NOT_REPORTED_FOR_QUARTER
    return AMBIGUOUS_CONCEPT if isinstance(exc, AmbiguousFactError) else MISSING_FACT


def _compare_unresolved_row(
    issuer: str, metric: str, reason: str, report_date: date | None = None
) -> TableRow:
    # A dated cell keeps its quarter, so a window table shows it on that quarter's row.
    return TableRow(
        company_name=issuer,
        ticker="",
        cik="",
        metric=metric,
        reason=reason,
        end_date=report_date,
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
            fetched = [
                facts.get_financials(issuer, component, report_date=report_date)
                for component in component_names
            ]
        except _LOOKUP_FAILURES as exc:
            rows.append(
                _compare_unresolved_row(
                    issuer, metric, _partial_lookup_reason(exc), report_date=report_date
                )
            )
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
        if (
            metric in FORMULA_COMPONENTS
            and metric not in DIFFERENCE_FORMULAS
            and metric not in SUM_FORMULAS
        ):
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
                newer_filing_end=max(
                    (
                        pending
                        for fact in fetched
                        if (pending := getattr(fact, "newer_filing_end", None))
                    ),
                    default=None,
                ),
            )
        )
    # Each row keeps its own issuer's period. When issuers' latest quarters end on
    # different dates the values stay visible, each with its own dates, and the
    # turn says the periods differ (see ``periods_differ``); no value is ever
    # computed across issuers.
    return rows


def _snapshot_date(as_of: str) -> date:
    return datetime.fromisoformat(as_of).date()


def market_formula_rows(
    facts: FactsPort,
    ranking: RankingPort,
    issuers: list[str],
    metric: str,
    *,
    report_date: date | None = None,
) -> list[TableRow]:
    """P/E: the snapshot's market cap over the trailing year's net income (ADR 0008).

    The snapshot holds one market cap, taken at its as_of date, so the ratio is
    given only for each company's latest trailing year; a past period gets
    ``LATEST_PERIOD_ONLY`` rather than today's price over old earnings.
    """
    snapshot_day = _snapshot_date(ranking.snapshot_as_of())
    source = ranking.snapshot_source()
    earnings_metric = FORMULA_COMPONENTS[metric][1]
    rows: list[TableRow] = []
    seen_ciks: set[str] = set()
    for issuer in issuers:
        try:
            member = ranking.lookup_member(issuer)
            latest = facts.get_financials(issuer, earnings_metric)
            earnings = (
                latest
                if report_date is None
                else facts.get_financials(issuer, earnings_metric, report_date=report_date)
            )
        except (*_LOOKUP_FAILURES, PerShareNotDerivableError) as exc:
            rows.append(
                _compare_unresolved_row(
                    issuer, metric, _partial_lookup_reason(exc), report_date=report_date
                )
            )
            continue
        if member.cik in seen_ciks:
            continue
        seen_ciks.add(member.cik)
        market_cap = ComponentProvenance(
            metric="market_cap",
            value=member.market_cap,
            start_date=snapshot_day,
            end_date=snapshot_day,
            form="",
            accession_number="",
            taxonomy="",
            concept="",
            source_url="",
            source=source,
        )
        components = [market_cap, _provenance_from_fact(earnings, earnings_metric)]
        period = {"start_date": earnings.start_date, "end_date": earnings.end_date}
        if earnings.end_date != latest.end_date:
            rows.append(
                _compare_row(
                    earnings, metric, components=components, reason=LATEST_PERIOD_ONLY, **period
                )
            )
            continue
        if earnings.value <= 0:
            rows.append(
                _compare_row(
                    earnings, metric, components=components, reason=NOT_MEANINGFUL, **period
                )
            )
            continue
        rows.append(
            _compare_row(
                earnings,
                metric,
                value=member.market_cap / earnings.value,
                components=components,
                newer_filing_end=getattr(earnings, "newer_filing_end", None),
                **period,
            )
        )
    return rows


def periods_differ(rows: list[TableRow]) -> bool:
    """Whether the valued rows cover different fiscal quarters."""
    periods = {(row.start_date, row.end_date) for row in rows if row.value is not None}
    return not _same_fiscal_period(periods)


def _rank_and_lookup_row(company: Any, index: int, metric: str, reason: str) -> TableRow:
    return TableRow(
        company_name=company.name,
        ticker=company.ticker,
        cik=company.cik,
        metric=metric,
        rank=index,
        reason=reason,
        market_cap=getattr(company, "market_cap", None),
    )


def _with_rank_identity(row: TableRow, company: Any, index: int) -> TableRow:
    return row.model_copy(
        update={
            "company_name": company.name,
            "ticker": company.ticker,
            "cik": company.cik,
            "rank": index,
            "market_cap": getattr(company, "market_cap", None),
        }
    )


def _rank_and_lookup_turn(plan: Any, runtime: Runtime) -> TurnResult:
    ranked = _ranked_table(plan, runtime, Intent.RANK_AND_LOOKUP)
    if isinstance(ranked, TurnResult):
        return ranked
    table, trace = ranked
    metric = plan.metric
    traces = [trace]
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
        banners=[snapshot_banner(table.as_of)],
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
    if metric in MARKET_FORMULAS:
        if runtime.ranking is None:
            raise RuntimeError(f"{metric} requires a ranking adapter for market cap")
        rows = market_formula_rows(
            runtime.facts, runtime.ranking, issuers, metric, report_date=report_date
        )
    else:
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
        banners=[PERIODS_DIFFER_BANNER] if periods_differ(rows) else [],
    )


def _snapshot_row(member: Any, metric: str, **kwargs: Any) -> TableRow:
    value = getattr(member, metric, None)
    return TableRow(
        company_name=member.name,
        ticker=member.ticker,
        cik=member.cik,
        metric=metric,
        value=value,
        currency="USD",
        reason=None if value is not None else MISSING_FACT,
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
        banners=[snapshot_banner(as_of)],
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
        fact = runtime.facts.get_financials(plan.company, metric, report_date=report_date)
    except _LOOKUP_FAILURES as exc:
        if isinstance(exc, PerShareNotDerivableError):
            # Not a failure: the filings say this figure exists only for the year.
            return TurnResult(
                intent=Intent.LOOKUP,
                tool_traces=[ToolTrace(tool="get_financials", args=args)],
                renderer=RendererKind.TABLE,
                table_rows=[
                    TableRow(
                        company_name=plan.company,
                        ticker="",
                        cik="",
                        metric=metric,
                        end_date=report_date,
                        reason=NOT_REPORTED_FOR_QUARTER,
                    )
                ],
            )
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
    if plan.intent in (
        Intent.EXPLAIN,
        Intent.FILING_CHANGE,
        Intent.NEWS_AND_EXPLAIN,
        Intent.EXPLORATORY_RESEARCH,
        Intent.RANK,
    ):
        return _run_workflow(plan, runtime, query=query)
    resolved = resolve_metric_phrase(query)
    if resolved.kind == "ambiguous":
        return _clarify_metric(plan.intent, resolved.candidates)
    if resolved.kind == "unknown":
        fallback = plan.metric if isinstance(plan.metric, str) else "unknown"
        term = fallback if fallback not in ALLOWED_METRICS else "unknown"
        return refuse_unknown_metric(plan.intent, term)
    if resolved.kind == "unique" and len(resolved.metrics) > 1:
        # One-shot execute_turn still clarifies; multi-metric composition runs
        # through run_spec_turn on the conversation seam (ticket 09).
        return _clarify_metric(plan.intent, resolved.metrics)
    if resolved.kind == "unique" and resolved.metric is not None:
        metric = resolved.metric
    else:
        metric = str(plan.metric or "")
    plan = _plan_with_metric(plan, metric)
    if plan.intent not in (Intent.COMPARE, Intent.RANK_AND_LOOKUP, Intent.LOOKUP):
        raise ValueError(f"unsupported intent: {plan.intent!r}")
    if metric not in ALLOWED_METRICS:
        return refuse_unknown_metric(plan.intent, metric)
    return _run_workflow(plan, runtime, query=query)


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
