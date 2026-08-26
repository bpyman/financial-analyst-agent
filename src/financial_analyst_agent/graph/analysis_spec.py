"""Analysis spec, patch application, validation, and task compilation.

Internal seams for the stateful analysis graph. Callers outside this package
should not depend on these helpers; the conversation seam owns the public API.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from financial_analyst_agent.contracts import ALLOWED_METRICS
from financial_analyst_agent.domain.errors import AmbiguousCompanyError, CompanyNotFoundError


class PeriodSelection(BaseModel):
    kind: Literal["latest_quarter"] = "latest_quarter"


class ResolvedCompany(BaseModel):
    cik: str
    name: str
    ticker: str
    query: str


class RankedSet(BaseModel):
    industry: str
    limit: int
    members: tuple[ResolvedCompany, ...] = ()


class AnalysisSpec(BaseModel):
    """Resolved quantitative statement of the analyst's current question."""

    companies: tuple[ResolvedCompany, ...] = ()
    constituents: RankedSet | None = None
    metrics: tuple[str, ...] = ()
    periods: PeriodSelection = Field(default_factory=PeriodSelection)
    operations: tuple[str, ...] = ()
    presentation: Literal["table"] = "table"


class SpecPatch(BaseModel):
    """Model-proposed edit. Deterministic code applies and resolves it."""

    mode: Literal["extend", "replace"]
    add_companies: tuple[str, ...] = ()
    remove_companies: tuple[str, ...] = ()
    add_metrics: tuple[str, ...] = ()
    remove_metrics: tuple[str, ...] = ()
    set_periods: PeriodSelection | None = None
    add_operations: tuple[str, ...] = ()
    remove_operations: tuple[str, ...] = ()
    set_presentation: Literal["table"] | None = None
    ranked_request: tuple[str, int] | None = None


class SpecDraft(BaseModel):
    """Unresolved patch outcome: company queries and metric slugs."""

    company_queries: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    periods: PeriodSelection = Field(default_factory=PeriodSelection)
    operations: tuple[str, ...] = ()
    presentation: Literal["table"] = "table"
    ranked_request: tuple[str, int] | None = None


class SpecRejection(BaseModel):
    code: Literal["invalid_metric", "empty_spec"]
    message: str


class CompiledTask(BaseModel):
    kind: Literal["lookup", "compare", "rank", "rank_and_lookup"]
    company_queries: tuple[str, ...] = ()
    metric: str | None = None
    industry: str | None = None
    limit: int | None = None


def _company_matches_token(company: ResolvedCompany, token: str) -> bool:
    needle = token.casefold()
    return needle in {
        company.query.casefold(),
        company.name.casefold(),
        company.ticker.casefold(),
        company.cik.casefold(),
    }


def apply_patch(current: AnalysisSpec | None, patch: SpecPatch) -> SpecDraft:
    """Apply a proposed patch to the current spec (or empty) → unresolved draft."""
    if patch.mode == "replace" or current is None:
        companies = list(patch.add_companies)
        metrics = list(patch.add_metrics)
        periods = patch.set_periods or PeriodSelection()
        operations = list(patch.add_operations)
        presentation = patch.set_presentation or "table"
        ranked = patch.ranked_request
    else:
        kept = [
            company
            for company in current.companies
            if not any(
                _company_matches_token(company, token) for token in patch.remove_companies
            )
        ]
        companies = [company.query for company in kept]
        for token in patch.add_companies:
            if token not in companies:
                companies.append(token)
        metrics = list(current.metrics)
        for slug in patch.remove_metrics:
            metrics = [m for m in metrics if m != slug]
        for slug in patch.add_metrics:
            if slug not in metrics:
                metrics.append(slug)
        periods = patch.set_periods or current.periods
        operations = list(current.operations)
        for op in patch.remove_operations:
            operations = [o for o in operations if o != op]
        for op in patch.add_operations:
            if op not in operations:
                operations.append(op)
        presentation = patch.set_presentation or current.presentation
        if patch.ranked_request is not None:
            ranked = patch.ranked_request
        elif current.constituents is not None:
            ranked = (current.constituents.industry, current.constituents.limit)
        else:
            ranked = None

    if ranked is not None:
        # Ranked constituents come from the ranking port; ignore model-typed lists.
        companies = []

    return SpecDraft(
        company_queries=tuple(companies),
        metrics=tuple(metrics),
        periods=periods,
        operations=tuple(operations),
        presentation=presentation,
        ranked_request=ranked,
    )


def resolve_spec(draft: SpecDraft, *, ranking: Any | None = None) -> AnalysisSpec:
    """Resolve company identity and ranked constituents. Metrics stay catalog slugs."""
    companies: list[ResolvedCompany] = []
    constituents: RankedSet | None = None

    if draft.ranked_request is not None:
        if ranking is None:
            raise RuntimeError("ranked analysis requires a ranking adapter")
        industry, limit = draft.ranked_request
        table = ranking.rank_companies(industry, limit)
        members = tuple(
            ResolvedCompany(
                cik=member.cik,
                name=member.name,
                ticker=member.ticker,
                query=member.ticker,
            )
            for member in table.companies
        )
        constituents = RankedSet(industry=industry, limit=limit, members=members)
    else:
        for query in draft.company_queries:
            companies.append(_resolve_company(query, ranking=ranking))

    operations = list(draft.operations)
    if len(companies) >= 2 and "across_companies" not in operations:
        operations.append("across_companies")
    if constituents is not None and "rank" not in operations:
        operations.append("rank")

    return AnalysisSpec(
        companies=tuple(companies),
        constituents=constituents,
        metrics=draft.metrics,
        periods=draft.periods,
        operations=tuple(operations),
        presentation=draft.presentation,
    )


def _resolve_company(query: str, *, ranking: Any | None) -> ResolvedCompany:
    if ranking is not None:
        try:
            member = ranking.lookup_member(query)
            return ResolvedCompany(
                cik=member.cik,
                name=member.name,
                ticker=member.ticker,
                query=query,
            )
        except (CompanyNotFoundError, AmbiguousCompanyError):
            # Lookup does not require freeze presence; keep the query token.
            pass
    return ResolvedCompany(cik="", name=query, ticker="", query=query)


def validate_spec(spec: AnalysisSpec) -> SpecRejection | None:
    """Validate a resolved spec against closed catalogs. No provider I/O."""
    for metric in spec.metrics:
        if metric not in ALLOWED_METRICS:
            return SpecRejection(
                code="invalid_metric",
                message=f"Unknown metric {metric!r}. Allowed: {', '.join(ALLOWED_METRICS)}",
            )
    has_companies = bool(spec.companies)
    has_constituents = spec.constituents is not None
    if not has_companies and not has_constituents:
        return SpecRejection(
            code="empty_spec",
            message="Analysis has no companies or ranked constituents",
        )
    if has_constituents and not spec.metrics:
        return None
    if not spec.metrics and has_companies:
        return SpecRejection(
            code="empty_spec",
            message="Analysis has no metrics",
        )
    return None


def compile_tasks(spec: AnalysisSpec) -> tuple[CompiledTask, ...]:
    """Compile a resolved spec into typed tasks without executing providers."""
    if spec.constituents is not None:
        if spec.metrics:
            metric = spec.metrics[0]
            return (
                CompiledTask(
                    kind="rank_and_lookup",
                    industry=spec.constituents.industry,
                    limit=spec.constituents.limit,
                    metric=metric,
                ),
            )
        return (
            CompiledTask(
                kind="rank",
                industry=spec.constituents.industry,
                limit=spec.constituents.limit,
            ),
        )

    queries = tuple(company.query for company in spec.companies)
    if not queries or not spec.metrics:
        return ()
    metric = spec.metrics[0]
    if len(queries) == 1:
        return (
            CompiledTask(
                kind="lookup",
                company_queries=queries,
                metric=metric,
            ),
        )
    return (
        CompiledTask(
            kind="compare",
            company_queries=queries,
            metric=metric,
        ),
    )
