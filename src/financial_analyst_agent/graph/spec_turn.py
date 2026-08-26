"""Execute a compiled analysis-spec task through existing closed workflows."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    MISSING_FACT,
    ComponentProvenance,
    Intent,
    RendererKind,
    Runtime,
    TableRow,
    ToolTrace,
    TurnResult,
)
from financial_analyst_agent.domain.errors import UnknownIndustryError
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    CompiledTask,
    SpecPatch,
    SpecRejection,
    apply_patch,
    compile_tasks,
    resolve_spec,
    validate_spec,
)
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase


def plan_to_spec_patch(plan: Any) -> SpecPatch:
    """Lift a one-shot closed Plan into a replace-mode spec patch."""
    intent = plan.intent
    if intent is Intent.LOOKUP:
        metric = plan.metric if isinstance(getattr(plan, "metric", None), str) else None
        return SpecPatch(
            mode="replace",
            add_companies=(plan.company,),
            add_metrics=(metric,) if metric else (),
        )
    if intent is Intent.COMPARE:
        metric = plan.metric if isinstance(getattr(plan, "metric", None), str) else None
        return SpecPatch(
            mode="replace",
            add_companies=tuple(plan.companies),
            add_metrics=(metric,) if metric else (),
            add_operations=("across_companies",),
        )
    if intent is Intent.RANK:
        industry = plan.industry or ""
        limit = int(getattr(plan, "limit", 10) or 10)
        return SpecPatch(mode="replace", ranked_request=(industry, limit))
    if intent is Intent.RANK_AND_LOOKUP:
        industry = plan.industry or ""
        limit = int(getattr(plan, "limit", 10) or 10)
        metric = plan.metric if isinstance(getattr(plan, "metric", None), str) else None
        return SpecPatch(
            mode="replace",
            ranked_request=(industry, limit),
            add_metrics=(metric,) if metric else (),
            add_operations=("rank",),
        )
    raise ValueError(f"cannot lift intent to spec patch: {intent!r}")


def bind_metrics_from_message(
    patch: SpecPatch, message: str, *, intent: Intent | None = None
) -> tuple[SpecPatch, TurnResult | None]:
    """Resolve metrics from the analyst's wording; never trust a model slug alone."""
    resolved = resolve_metric_phrase(message)
    effective_intent = intent or Intent.LOOKUP
    if resolved.kind == "ambiguous":
        return patch, TurnResult(
            intent=effective_intent,
            tool_traces=[],
            renderer=RendererKind.CLARIFY,
            candidates=resolved.candidates,
        )
    phrased: tuple[str, ...] = ()
    if resolved.kind == "unique":
        if resolved.metrics:
            phrased = resolved.metrics
        elif resolved.metric is not None:
            phrased = (resolved.metric,)
    if phrased:
        if patch.mode == "replace":
            return patch.model_copy(update={"add_metrics": phrased}), None
        # Extend: add phrased metrics except those this patch is removing.
        to_add = tuple(m for m in phrased if m not in patch.remove_metrics)
        metrics = tuple(dict.fromkeys([*patch.add_metrics, *to_add]))
        return patch.model_copy(update={"add_metrics": metrics}), None
    # No metric phrase in the analyst's wording.
    if patch.mode == "extend":
        return patch, None
    if patch.ranked_request is not None and not patch.add_metrics:
        return patch, None
    # Replace-mode metric question with an unknown phrase: refuse like execute_turn
    # even when the planner guessed a catalog slug.
    term = "unknown"
    if patch.add_metrics:
        candidate = patch.add_metrics[0]
        if candidate not in ALLOWED_METRICS:
            term = candidate
    allowed = ", ".join(ALLOWED_METRICS)
    return patch, TurnResult(
        intent=effective_intent,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=f"Unknown metric {term!r}. Allowed: {allowed}",
    )


def is_qualitative_proposal(proposal: Any) -> bool:
    if isinstance(proposal, SpecPatch):
        return False
    intent = getattr(proposal, "intent", None)
    return intent in (Intent.EXPLAIN, Intent.NEWS_AND_EXPLAIN)


def is_structured_proposal(proposal: Any) -> bool:
    if isinstance(proposal, SpecPatch):
        return True
    intent = getattr(proposal, "intent", None)
    return intent in (
        Intent.LOOKUP,
        Intent.COMPARE,
        Intent.RANK,
        Intent.RANK_AND_LOOKUP,
    )


def _rejection_result(rejection: SpecRejection) -> TurnResult:
    return TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=rejection.message,
    )


def execute_compiled_task(
    task: CompiledTask, runtime: Runtime, *, query: str = ""
) -> TurnResult:
    from financial_analyst_agent.graph import run_workflow_turn

    if task.kind == "lookup":
        plan = SimpleNamespace(
            intent=Intent.LOOKUP,
            company=task.company_queries[0],
            companies=[],
            metric=task.metric,
            industry=None,
            limit=10,
            topic=None,
            report_date=task.report_date,
        )
        return run_workflow_turn(plan, runtime, query=query)
    if task.kind == "compare":
        plan = SimpleNamespace(
            intent=Intent.COMPARE,
            company=None,
            companies=list(task.company_queries),
            metric=task.metric,
            industry=None,
            limit=10,
            topic=None,
            report_date=task.report_date,
        )
        return run_workflow_turn(plan, runtime, query=query)
    if task.kind == "rank":
        plan = SimpleNamespace(
            intent=Intent.RANK,
            company=None,
            companies=[],
            metric=None,
            industry=task.industry,
            limit=task.limit or 10,
            topic=None,
        )
        return run_workflow_turn(plan, runtime, query=query)
    if task.kind == "rank_and_lookup":
        plan = SimpleNamespace(
            intent=Intent.RANK_AND_LOOKUP,
            company=None,
            companies=[],
            metric=task.metric,
            industry=task.industry,
            limit=task.limit or 10,
            topic=None,
        )
        return run_workflow_turn(plan, runtime, query=query)
    raise ValueError(f"unsupported compiled task: {task.kind!r}")


def _lookup_refuse_as_partial(task: CompiledTask, result: TurnResult) -> list[TableRow]:
    """Convert a whole-lookup refuse into a cell so multi-metric tables stay partial."""
    if result.renderer is not RendererKind.REFUSE:
        return list(result.table_rows)
    if task.kind != "lookup" or not task.company_queries or not task.metric:
        return list(result.table_rows)
    return [
        TableRow(
            company_name=task.company_queries[0],
            ticker="",
            cik="",
            metric=task.metric,
            end_date=task.report_date,
            reason=MISSING_FACT,
        )
    ]


def _provenance_from_level(row: TableRow) -> ComponentProvenance:
    if row.components:
        return row.components[0]
    assert row.value is not None
    assert row.start_date is not None
    assert row.end_date is not None
    return ComponentProvenance(
        metric=row.metric,
        value=row.value,
        start_date=row.start_date,
        end_date=row.end_date,
        form=row.form or "",
        accession_number=row.accession_number or "",
        taxonomy=row.taxonomy or "",
        concept=row.concept or row.metric,
        source_url=row.source_url or "",
        source="sec_xbrl",
    )


def _change_row(current: TableRow, prior: TableRow, *, comparison: str) -> TableRow:
    from decimal import Decimal

    assert current.value is not None and prior.value is not None
    return TableRow(
        company_name=current.company_name,
        ticker=current.ticker,
        cik=current.cik,
        metric=current.metric,
        value=Decimal(str(current.value)) - Decimal(str(prior.value)),
        currency=current.currency,
        start_date=prior.start_date,
        end_date=current.end_date,
        components=[_provenance_from_level(prior), _provenance_from_level(current)],
        comparison=comparison,  # type: ignore[arg-type]
    )


def _yoy_prior_date(end: date) -> date:
    try:
        return end.replace(year=end.year - 1)
    except ValueError:
        # Feb 29 → Feb 28 prior year
        return end.replace(year=end.year - 1, day=28)


def across_period_change_rows(levels: list[TableRow]) -> list[TableRow]:
    """Sequential and year-over-year change from period-aligned level cells."""
    by_key: dict[tuple[str, str], list[TableRow]] = {}
    for row in levels:
        if row.value is None or row.end_date is None or row.comparison is not None:
            continue
        by_key.setdefault((row.cik or row.company_name, row.metric), []).append(row)

    changes: list[TableRow] = []
    for group in by_key.values():
        ordered = sorted(group, key=lambda r: r.end_date or date.min, reverse=True)
        for newer, older in zip(ordered, ordered[1:], strict=False):
            changes.append(_change_row(newer, older, comparison="sequential"))
        by_end = {row.end_date: row for row in ordered if row.end_date is not None}
        for row in ordered:
            if row.end_date is None:
                continue
            prior = by_end.get(_yoy_prior_date(row.end_date))
            if prior is None or prior is row:
                continue
            changes.append(_change_row(row, prior, comparison="yoy"))
    return changes


def merge_task_results(
    tasks: tuple[CompiledTask, ...],
    results: list[TurnResult],
    *,
    across_periods: bool = False,
) -> TurnResult:
    """Assemble independent cell results into one analysis table."""
    if len(results) == 1 and not across_periods:
        return results[0]

    rows: list[TableRow] = []
    traces: list[ToolTrace] = []
    banners: list[str] = []
    for task, result in zip(tasks, results, strict=True):
        if result.renderer is RendererKind.REFUSE and not result.table_rows:
            rows.extend(_lookup_refuse_as_partial(task, result))
            continue
        rows.extend(result.table_rows)
        traces.extend(result.tool_traces)
        for banner in result.banners:
            if banner not in banners:
                banners.append(banner)

    if not rows and any(r.renderer is RendererKind.REFUSE for r in results):
        # Every task refused with no cells — surface the first refuse.
        for result in results:
            if result.renderer is RendererKind.REFUSE:
                return result

    if across_periods:
        rows = list(rows) + across_period_change_rows(rows)

    intent = results[0].intent
    if any(task.kind == "compare" for task in tasks):
        intent = Intent.COMPARE
    elif any(task.kind == "rank_and_lookup" for task in tasks):
        intent = Intent.RANK_AND_LOOKUP
    elif any(task.kind == "rank" for task in tasks):
        intent = Intent.RANK

    return TurnResult(
        intent=intent,
        tool_traces=traces,
        renderer=RendererKind.TABLE,
        table_rows=rows,
        banners=banners,
    )


def run_spec_turn(
    message: str,
    runtime: Runtime,
    *,
    current_spec: AnalysisSpec | None,
    proposal: Any,
) -> tuple[TurnResult, AnalysisSpec | None, SpecPatch]:
    """Apply a structured proposal: patch → resolve → validate → compile → execute."""
    patch = (
        proposal
        if isinstance(proposal, SpecPatch)
        else plan_to_spec_patch(proposal)
    )
    intent = getattr(proposal, "intent", None) if not isinstance(proposal, SpecPatch) else None
    patch, early = bind_metrics_from_message(patch, message, intent=intent)
    if early is not None:
        return early, current_spec, patch

    draft = apply_patch(current_spec, patch)
    # Drop model-supplied metrics that are not in the catalog when wording did not
    # resolve a unique phrase (plan slug may still be present on replace).
    if draft.metrics and any(m not in ALLOWED_METRICS for m in draft.metrics):
        bad = next(m for m in draft.metrics if m not in ALLOWED_METRICS)
        return (
            _rejection_result(
                SpecRejection(
                    code="invalid_metric",
                    message=(
                        f"Unknown metric {bad!r}. Allowed: {', '.join(ALLOWED_METRICS)}"
                    ),
                )
            ),
            None,
            patch,
        )

    try:
        spec = resolve_spec(draft, ranking=runtime.ranking)
    except UnknownIndustryError as exc:
        return (
            TurnResult(
                intent=Intent.RANK
                if draft.ranked_request is not None and not draft.metrics
                else Intent.RANK_AND_LOOKUP
                if draft.ranked_request is not None
                else Intent.LOOKUP,
                tool_traces=[],
                renderer=RendererKind.REFUSE,
                message=str(exc),
            ),
            None,
            patch,
        )
    outcome = validate_spec(spec)
    if outcome is not None:
        return _rejection_result(outcome), None, patch

    tasks = compile_tasks(spec)
    if not tasks:
        return (
            _rejection_result(
                SpecRejection(code="empty_spec", message="Analysis compiled to no tasks")
            ),
            None,
            patch,
        )

    results = [execute_compiled_task(task, runtime, query=message) for task in tasks]
    across = "across_periods" in spec.operations
    return merge_task_results(tasks, results, across_periods=across), spec, patch
