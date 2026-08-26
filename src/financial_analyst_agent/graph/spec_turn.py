"""Execute a compiled analysis-spec task through existing closed workflows."""

from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from financial_analyst_agent.domain.errors import (
    CompanyNotFoundError,
    ProviderError,
    UnknownIndustryError,
)
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    CompiledTask,
    PeriodSelection,
    SpecPatch,
    SpecRejection,
    apply_patch,
    compile_tasks,
    resolve_spec,
    validate_spec,
)
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase

_ADD_EDIT = re.compile(
    r"^\s*(?:now\s+)?(?:also\s+)?(?:add|include)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_DROP_EDIT = re.compile(
    r"^\s*(?:drop|remove|without)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_SWAP_EDIT = re.compile(
    r"^\s*(?:use|swap)\s+(.+?)\s+instead of\s+(.+?)\s*$",
    re.IGNORECASE,
)
_LAST_N_QUARTERS = re.compile(
    r"\blast\s+(\d+|two|three|four|five|six|eight)\s+quarters?\b",
    re.IGNORECASE,
)
_YOY = re.compile(
    r"\b(?:year[\s-]*over[\s-]*year|yoy|show yoy|compare to last year)\b",
    re.IGNORECASE,
)
_STANDALONE_LOOKUP = re.compile(
    r"^\s*what(?:'s| is| was)\b",
    re.IGNORECASE,
)
_STANDALONE_COMPARE = re.compile(
    r"^\s*compare\s+(?!to\b).+\band\b",
    re.IGNORECASE,
)
_COMPARE_TO_ISSUER = re.compile(
    r"^\s*compare\s+to\s+(.+?)\s*$",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "eight": 8,
}

# Bound concurrent provider fan-out so a wide window cannot flood SEC/EDGAR.
DEFAULT_TASK_MAX_WORKERS = 8

ProgressCallback = Callable[[int, int], None]


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


def _unique_metrics_from_phrase(text: str) -> tuple[str, ...]:
    resolved = resolve_metric_phrase(text)
    if resolved.kind != "unique":
        return ()
    if resolved.metrics:
        return resolved.metrics
    if resolved.metric is not None:
        return (resolved.metric,)
    return ()


def _company_tokens(text: str) -> tuple[str, ...]:
    parts = re.split(r"\s+and\s+|,\s*", text, flags=re.IGNORECASE)
    return tuple(part.strip(" .,") for part in parts if part.strip(" .,"))


def _period_count_from_match(match: re.Match[str] | None, *, yoy: bool) -> int:
    if match is not None:
        raw = match.group(1).casefold()
        count = _NUMBER_WORDS.get(raw, int(raw) if raw.isdigit() else 4)
    else:
        count = 5
    if yoy and count < 5:
        return 5
    return count


def bind_periods_from_message(patch: SpecPatch, message: str) -> SpecPatch:
    """Period windows come from the analyst's wording, not a model slug."""
    match = _LAST_N_QUARTERS.search(message)
    yoy = _YOY.search(message) is not None
    if match is None and not yoy:
        return patch
    operations = patch.add_operations
    if yoy and "across_periods" not in operations:
        operations = (*operations, "across_periods")
    if match is None and patch.set_periods is not None:
        return patch.model_copy(update={"add_operations": operations})
    count = _period_count_from_match(match, yoy=yoy)
    return patch.model_copy(
        update={
            "set_periods": PeriodSelection(kind="last_n_quarters", count=count),
            "add_operations": operations,
        }
    )


def refine_patch_from_message(
    patch: SpecPatch,
    message: str,
    current_spec: AnalysisSpec | None,
) -> SpecPatch:
    """Turn follow-up wording into an extend patch when the planner still replaced."""
    patch = bind_periods_from_message(patch, message)
    if current_spec is None:
        return patch

    swapped = _SWAP_EDIT.match(message.strip())
    if swapped is not None:
        incoming = swapped.group(1).strip()
        outgoing = swapped.group(2).strip()
        add_metrics = _unique_metrics_from_phrase(incoming)
        remove_metrics = _unique_metrics_from_phrase(outgoing)
        if add_metrics and remove_metrics:
            return patch.model_copy(
                update={
                    "mode": "extend",
                    "add_metrics": add_metrics,
                    "remove_metrics": remove_metrics,
                    "add_companies": (),
                    "remove_companies": (),
                    "ranked_request": None,
                }
            )
        return patch.model_copy(
            update={
                "mode": "extend",
                "add_companies": (incoming,),
                "remove_companies": (outgoing,),
                "add_metrics": (),
                "ranked_request": None,
            }
        )

    added = _ADD_EDIT.match(message.strip())
    if added is not None:
        token = added.group(1).strip(" .,")
        metrics = _unique_metrics_from_phrase(token)
        if metrics:
            return patch.model_copy(
                update={
                    "mode": "extend",
                    "add_metrics": metrics,
                    "add_companies": (),
                    "ranked_request": None,
                }
            )
        resolved = resolve_metric_phrase(token)
        if resolved.kind == "ambiguous":
            return patch.model_copy(
                update={
                    "mode": "extend",
                    "add_companies": (),
                    "ranked_request": None,
                }
            )
        if patch.add_metrics and not patch.add_companies:
            return patch.model_copy(
                update={
                    "mode": "extend",
                    "add_companies": (),
                    "ranked_request": None,
                }
            )
        companies = _company_tokens(token)
        return patch.model_copy(
            update={
                "mode": "extend",
                "add_companies": companies,
                "add_metrics": (),
                "ranked_request": None,
            }
        )

    dropped = _DROP_EDIT.match(message.strip())
    if dropped is not None:
        token = dropped.group(1).strip(" .,")
        metrics = _unique_metrics_from_phrase(token)
        if metrics:
            return patch.model_copy(
                update={
                    "mode": "extend",
                    "remove_metrics": metrics,
                    "add_metrics": (),
                    "add_companies": (),
                    "ranked_request": None,
                }
            )
        resolved = resolve_metric_phrase(token)
        if resolved.kind == "ambiguous":
            return patch.model_copy(
                update={
                    "mode": "extend",
                    "add_companies": (),
                    "remove_companies": (),
                    "add_metrics": (),
                    "ranked_request": None,
                }
            )
        companies = _company_tokens(token)
        return patch.model_copy(
            update={
                "mode": "extend",
                "remove_companies": companies,
                "add_metrics": (),
                "add_companies": (),
                "ranked_request": None,
            }
        )

    compare_to = _COMPARE_TO_ISSUER.match(message.strip())
    if compare_to is not None and _YOY.search(message) is None:
        token = compare_to.group(1).strip(" .,")
        if token and not _unique_metrics_from_phrase(token):
            return patch.model_copy(
                update={
                    "mode": "extend",
                    "add_companies": (token,),
                    "add_metrics": (),
                    "ranked_request": None,
                }
            )

    standalone = (
        _STANDALONE_LOOKUP.search(message.strip()) is not None
        or _STANDALONE_COMPARE.search(message.strip()) is not None
    )
    if patch.set_periods is not None and patch.mode == "replace" and not standalone:
        return patch.model_copy(
            update={
                "mode": "extend",
                "add_companies": (),
                "add_metrics": (),
                "ranked_request": None,
            }
        )
    if standalone and _YOY.search(message) is None:
        return patch.model_copy(
            update={
                "mode": "replace",
                "remove_companies": (),
                "remove_metrics": (),
            }
        )
    return patch


def materialize_period_dates(spec: AnalysisSpec, runtime: Runtime) -> AnalysisSpec:
    """Fill last_n_quarters report_dates from the facts port when the patch omitted them."""
    if spec.periods.kind != "last_n_quarters" or spec.periods.report_dates:
        return spec
    count = spec.periods.count or 1
    listing = getattr(runtime.facts, "list_quarterly_report_dates", None)
    if listing is None:
        return spec
    company = ""
    if spec.companies:
        company = spec.companies[0].query
    elif spec.constituents is not None and spec.constituents.members:
        company = spec.constituents.members[0].query
    if not company:
        return spec
    try:
        dates = tuple(listing(company, limit=count))
    except (AttributeError, TypeError):
        return spec
    if not dates:
        return spec
    return spec.model_copy(
        update={
            "periods": spec.periods.model_copy(
                update={"count": len(dates), "report_dates": dates}
            )
        }
    )


def is_qualitative_proposal(proposal: Any) -> bool:
    if isinstance(proposal, SpecPatch):
        return False
    intent = getattr(proposal, "intent", None)
    return intent in (
        Intent.EXPLAIN,
        Intent.NEWS_AND_EXPLAIN,
        Intent.EXPLORATORY_RESEARCH,
    )


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


def _task_failure_result(task: CompiledTask, exc: BaseException) -> TurnResult:
    """Isolate an unexpected cell failure as a typed partial or refuse."""
    if task.kind == "lookup" and task.company_queries and task.metric:
        return TurnResult(
            intent=Intent.LOOKUP,
            tool_traces=[],
            renderer=RendererKind.TABLE,
            table_rows=[
                TableRow(
                    company_name=task.company_queries[0],
                    ticker="",
                    cik="",
                    metric=task.metric,
                    end_date=task.report_date,
                    reason=MISSING_FACT,
                )
            ],
        )
    if task.kind == "compare" and task.company_queries and task.metric:
        return TurnResult(
            intent=Intent.COMPARE,
            tool_traces=[],
            renderer=RendererKind.TABLE,
            table_rows=[
                TableRow(
                    company_name=company,
                    ticker="",
                    cik="",
                    metric=task.metric,
                    end_date=task.report_date,
                    reason=MISSING_FACT,
                )
                for company in task.company_queries
            ],
        )
    return TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=str(exc),
    )


def dispatch_compiled_tasks(
    tasks: tuple[CompiledTask, ...],
    runtime: Runtime,
    *,
    query: str = "",
    on_progress: ProgressCallback | None = None,
    max_workers: int = DEFAULT_TASK_MAX_WORKERS,
) -> list[TurnResult]:
    """Run independent compiled tasks concurrently; preserve task order in results.

    Worker count is capped so a wide company × metric × period fan-out cannot
    open unbounded provider connections. Completion order does not affect merge
    order: results are always returned in ``tasks`` order.
    """
    total = len(tasks)
    if total == 0:
        return []
    if total == 1 or max_workers <= 1:
        results: list[TurnResult] = []
        for index, task in enumerate(tasks):
            try:
                results.append(execute_compiled_task(task, runtime, query=query))
            except Exception as exc:
                results.append(_task_failure_result(task, exc))
            if on_progress is not None:
                on_progress(index + 1, total)
        return results

    workers = min(max_workers, total)
    ordered: list[TurnResult | None] = [None] * total
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(execute_compiled_task, task, runtime, query=query): index
            for index, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                ordered[index] = future.result()
            except Exception as exc:
                ordered[index] = _task_failure_result(tasks[index], exc)
            done += 1
            if on_progress is not None:
                on_progress(done, total)
    assert all(result is not None for result in ordered)
    return [result for result in ordered if result is not None]


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
    on_progress: ProgressCallback | None = None,
    max_workers: int = DEFAULT_TASK_MAX_WORKERS,
) -> tuple[TurnResult, AnalysisSpec | None, SpecPatch]:
    """Apply a structured proposal: patch → resolve → validate → compile → execute."""
    patch = (
        proposal
        if isinstance(proposal, SpecPatch)
        else plan_to_spec_patch(proposal)
    )
    intent = getattr(proposal, "intent", None) if not isinstance(proposal, SpecPatch) else None
    patch = refine_patch_from_message(patch, message, current_spec)
    if patch.mode is None:
        if current_spec is None:
            patch = patch.model_copy(update={"mode": "replace"})
        else:
            effective = intent or Intent.LOOKUP
            return (
                TurnResult(
                    intent=effective,
                    tool_traces=[],
                    renderer=RendererKind.CLARIFY,
                    candidates=("extend", "replace"),
                ),
                current_spec,
                patch,
            )
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

    try:
        spec = materialize_period_dates(spec, runtime)
    except (CompanyNotFoundError, ProviderError) as exc:
        return (
            TurnResult(
                intent=Intent.LOOKUP,
                tool_traces=[],
                renderer=RendererKind.REFUSE,
                message=str(exc),
            ),
            None,
            patch,
        )
    if spec.periods.kind == "last_n_quarters" and not spec.periods.report_dates:
        return (
            _rejection_result(
                SpecRejection(
                    code="empty_spec",
                    message=(
                        "Could not determine quarterly report dates "
                        "for the requested window"
                    ),
                )
            ),
            None,
            patch,
        )
    tasks = compile_tasks(spec)
    if not tasks:
        return (
            _rejection_result(
                SpecRejection(code="empty_spec", message="Analysis compiled to no tasks")
            ),
            None,
            patch,
        )

    results = dispatch_compiled_tasks(
        tasks,
        runtime,
        query=message,
        on_progress=on_progress,
        max_workers=max_workers,
    )
    across = "across_periods" in spec.operations
    return merge_task_results(tasks, results, across_periods=across), spec, patch
