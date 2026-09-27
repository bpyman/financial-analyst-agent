"""Execute a compiled analysis-spec task through existing closed workflows."""

from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    MISSING_FACT,
    QUALITATIVE_INTENTS,
    SOURCE_UNAVAILABLE,
    STRUCTURED_INTENTS,
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
    SessionQuotaError,
    UnknownIndustryError,
)
from financial_analyst_agent.graph.analysis_spec import (
    MAX_RANKED_COMPANIES,
    AnalysisSpec,
    CompiledTask,
    NamedPeriodSpec,
    PeriodSelection,
    SpecPatch,
    SpecRejection,
    apply_patch,
    calendar_groups,
    compile_tasks,
    resolve_spec,
    validate_spec,
)
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
from financial_analyst_agent.services.fiscal_periods import dates_for
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
    r"\b(?:year[\s-]*over[\s-]*year|yoy|show yoy|compare to last year"
    r"|(?:over|in) the (?:last|past) year|(?:from|since|vs\.?|versus) (?:a year ago|last year)"
    r"|grow(?:th|n|ing)?|grew|how (?:has|have|did) .+ change[d]?|trend(?:ing)?)\b",
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
_YEAR = r"'?(?P<y>(?:19|20)\d{2}|\d{2})\b"
_FISCAL_WORD = r"(?:(?:fy|fiscal(?:\s+year)?)\s*)?"
_CALENDAR_WORD = r"(?P<cal>calendar\s+(?:year\s+)?|cy\s*)?"
_QUARTER_WORDS = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
}
# Named periods, most specific first: "Q3 2024", "Q3 FY25", "2024 Q3", "third
# quarter of fiscal 2024", "fiscal 2025", "FY24", "calendar 2025", "in 2024".
_NAMED_PERIOD_PATTERNS = (
    re.compile(rf"\b{_CALENDAR_WORD}q(?P<q>[1-4])\s*(?:of\s+)?{_FISCAL_WORD}{_YEAR}", re.I),
    re.compile(rf"\b{_CALENDAR_WORD}(?P<y>(?:19|20)\d{{2}})\s*q(?P<q>[1-4])\b", re.I),
    # Sell-side shorthand: "2Q 2026", "3Q25", "4QFY24".
    re.compile(rf"\b{_CALENDAR_WORD}(?P<q>[1-4])q\s*{_FISCAL_WORD}{_YEAR}", re.I),
    re.compile(
        rf"\b{_CALENDAR_WORD}(?P<qw>first|second|third|fourth|1st|2nd|3rd|4th)\s+"
        rf"(?:fiscal\s+)?quarter\s+(?:of\s+)?{_FISCAL_WORD}{_YEAR}",
        re.I,
    ),
    re.compile(rf"\b(?P<cal>calendar(?:\s+year)?\s+|cy\s*){_YEAR}", re.I),
    re.compile(rf"\b(?:fy|fiscal(?:\s+year)?)\s*{_YEAR}", re.I),
    re.compile(r"\b(?:in|for|during)\s+(?P<y>(?:19|20)\d{2})\b", re.I),
)
# Wording that asks for year-over-year change only, not quarter-to-quarter too.
_EXPLICIT_YOY = re.compile(
    r"\b(?:year[\s-]*over[\s-]*year|yoy"
    r"|(?:from|since|vs\.?|versus|compared? (?:to|with)) "
    r"(?:a year ago|last year|the (?:prior|previous) year))\b",
    re.IGNORECASE,
)
_SEQUENTIAL = re.compile(r"\b(?:sequential|quarter[\s-]*over[\s-]*quarter|qoq)\b", re.IGNORECASE)
# Four quarters, each with the quarter a year before it.
_YOY_WINDOW = 8
# "Q5 2025" names no quarter; answering the latest one instead would mislead.
_INVALID_QUARTER = re.compile(r"\bQ(0|[5-9]|\d{2,})\s*(?:FY\s*)?'?\d{2,4}\b", re.IGNORECASE)
# "latest revenue" after "Apple revenue Q3 2025" asks for the newest quarter again.
_LATEST = re.compile(r"\b(?:latest|most recent|newest)\b", re.IGNORECASE)
_TRAILING_YEAR = re.compile(
    r"\b(?:ttm|ltm|trailing[\s-]+(?:twelve|12)[\s-]+months?|(?:last|past)\s+(?:twelve|12)\s+months)\b",
    re.I,
)
TRAILING_YEAR_BANNER = (
    "Trailing twelve months: these are the four latest quarters, shown one by one "
    "rather than summed."
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


@dataclass(frozen=True)
class TurnContext:
    """Bundled inputs that travel together into a spec turn."""

    message: str
    current_spec: AnalysisSpec | None
    proposal: Any
    on_progress: ProgressCallback | None = None
    max_workers: int = DEFAULT_TASK_MAX_WORKERS


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
        ordered = getattr(plan, "order_by_metric", False) is True
        return SpecPatch(
            mode="replace",
            ranked_request=(industry, limit),
            add_metrics=(metric,) if metric else (),
            add_operations=("rank", "order_by_metric") if ordered else ("rank",),
        )
    raise ValueError(f"cannot lift intent to spec patch: {intent!r}")


# Wording that asks for numbers without naming a metric. Each maps to the
# metrics that answer it, so the window shows data instead of a refusal.
OVERVIEW_METRICS: tuple[str, ...] = (
    "revenue",
    "net_income",
    "gross_margin",
    "operating_margin",
    "net_margin",
)
_BIGGER = re.compile(r"\b(?:bigger|larger|biggest|largest|size)\b", re.IGNORECASE)
_PROFITABLE = re.compile(r"\b(?:more|most|less|least)?\s*profitab(?:le|ility)\b", re.IGNORECASE)
_GROWING = re.compile(
    r"\b(?:grow(?:ing|n|th)?|grew|changed?|trend(?:ing)?|doing over time)\b", re.IGNORECASE
)
_OVERVIEW = re.compile(
    r"\b(?:overview|snapshot|summary|profile|financials|fundamentals|numbers|"
    r"key metrics|at a glance|tell me about|how (?:is|are|was)|how's|doing|results)\b",
    re.IGNORECASE,
)
_OVERVIEW_MAX_WORDS = 3
# A planner's metric for "Compare Nvidia and AMD": companies and nothing else.
OVERVIEW_PLAN = "overview"


def implied_metrics(message: str) -> tuple[str, ...]:
    """Metrics a question implies when it names none ("Which is bigger?")."""
    if _BIGGER.search(message):
        return ("market_cap", "revenue")
    if _PROFITABLE.search(message):
        return ("net_income", "net_margin")
    if _GROWING.search(message):
        return ("revenue",)
    if _OVERVIEW.search(message) or len(message.split()) <= _OVERVIEW_MAX_WORDS:
        return OVERVIEW_METRICS
    return ()


def _names_companies(patch: SpecPatch) -> bool:
    return (
        patch.ranked_request is None
        and bool(patch.add_companies)
        and all(company and company != "unknown" for company in patch.add_companies)
    )


def _names_new_subject(patch: SpecPatch, spec: AnalysisSpec) -> bool:
    """Whether the patch names a company or ranking the current analysis lacks.

    A model planner often repeats the current company in a follow-up's plan, so
    naming a company already on screen is not a new question.
    """
    if patch.ranked_request is not None:
        return spec.constituents is None or (
            patch.ranked_request[0].casefold() != spec.constituents.industry.casefold()
        )
    if not _names_companies(patch):
        return False
    known = {
        label.casefold()
        for company in spec.companies
        for label in (company.query, company.name, company.ticker)
    }
    return any(company.casefold() not in known for company in patch.add_companies)


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
    guessed = [metric for metric in patch.add_metrics if metric in ALLOWED_METRICS]
    implied = implied_metrics(message) if _names_companies(patch) and not guessed else ()
    if not implied and _names_companies(patch) and OVERVIEW_PLAN in patch.add_metrics:
        implied = OVERVIEW_METRICS
    if implied:
        return patch.model_copy(update={"add_metrics": implied}), None
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


def parse_named_periods(message: str) -> tuple[NamedPeriodSpec, ...]:
    """Every period the message names, in the order named, without repeats."""
    found: list[tuple[int, NamedPeriodSpec]] = []
    taken: list[tuple[int, int]] = []
    for pattern in _NAMED_PERIOD_PATTERNS:
        for match in pattern.finditer(message):
            start, end = match.span()
            if any(start < other_end and end > other_start for other_start, other_end in taken):
                continue
            groups = match.groupdict()
            raw_year = groups["y"]
            year = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
            quarter = None
            if groups.get("q"):
                quarter = int(groups["q"])
            elif groups.get("qw"):
                quarter = _QUARTER_WORDS[groups["qw"].casefold()]
            taken.append((start, end))
            found.append(
                (
                    start,
                    NamedPeriodSpec(year=year, quarter=quarter, calendar=bool(groups.get("cal"))),
                )
            )
    ordered = [period for _start, period in sorted(found, key=lambda item: item[0])]
    return tuple(dict.fromkeys(ordered))


def _with_year_earlier(named: tuple[NamedPeriodSpec, ...]) -> tuple[NamedPeriodSpec, ...]:
    """Add the same period a year earlier, so a year-over-year change has a base."""
    earlier = [period.model_copy(update={"year": period.year - 1}) for period in named]
    return tuple(dict.fromkeys([*named, *earlier]))


def bind_periods_from_message(patch: SpecPatch, message: str) -> SpecPatch:
    """Period windows come from the analyst's wording, not a model slug."""
    match = _LAST_N_QUARTERS.search(message)
    yoy = _YOY.search(message) is not None
    named = parse_named_periods(message)
    if not named and match is None and not yoy and _TRAILING_YEAR.search(message):
        # "TTM revenue": show the four quarters that make up the trailing year.
        return patch.model_copy(
            update={"set_periods": PeriodSelection(kind="last_n_quarters", count=4)}
        )
    if named:
        operations = patch.add_operations
        quarters = [period for period in named if period.quarter is not None]
        if yoy:
            named = _with_year_earlier(named)
        if (yoy or len(quarters) >= 2) and "across_periods" not in operations:
            operations = (*operations, "across_periods")
        return patch.model_copy(
            update={
                "set_periods": PeriodSelection(kind="named", named=named),
                "add_operations": operations,
            }
        )
    if match is None and not yoy:
        if _LATEST.search(message) is not None:
            return patch.model_copy(
                update={
                    "set_periods": PeriodSelection(),
                    "remove_operations": (*patch.remove_operations, "across_periods"),
                }
            )
        return patch
    operations = patch.add_operations
    if yoy and "across_periods" not in operations:
        operations = (*operations, "across_periods")
    explicit_yoy = _EXPLICIT_YOY.search(message) is not None and not _SEQUENTIAL.search(message)
    if explicit_yoy and "year_over_year" not in operations:
        operations = (*operations, "year_over_year")
    if match is None and patch.set_periods is not None:
        return patch.model_copy(update={"add_operations": operations})
    count = _period_count_from_match(match, yoy=yoy)
    if explicit_yoy and match is None:
        count = _YOY_WINDOW
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
    # A period on its own ("for Q3 2024", "last 8 quarters") edits the current
    # analysis. One that names another company or ranking ("Microsoft TTM net
    # income") is a new question and keeps what it names.
    period_only = not _names_new_subject(patch, current_spec)
    if patch.set_periods is not None and patch.mode == "replace" and not standalone and period_only:
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


def _listed_dates(listing: Any, company: str, count: int) -> tuple[date, ...]:
    try:
        return tuple(listing(company, limit=count))
    except (AttributeError, TypeError):
        return ()


def materialize_period_dates(spec: AnalysisSpec, runtime: Runtime) -> AnalysisSpec:
    """Fill last_n_quarters report dates from the facts port.

    The first company's quarter ends become ``report_dates``; every other named
    company gets its own, so a company on a different fiscal calendar is asked
    for its quarters rather than the first company's. Dates already on the spec
    are kept, so a follow-up that adds a company lists only that company.
    """
    if spec.periods.kind == "named":
        return _materialize_named_periods(spec, runtime)
    if spec.periods.kind != "last_n_quarters":
        return spec
    listing = getattr(runtime.facts, "list_quarterly_report_dates", None)
    if listing is None:
        return spec
    queries = [company.query for company in spec.companies]
    if not queries and spec.constituents is not None and spec.constituents.members:
        queries = [spec.constituents.members[0].query]
    if not queries:
        return spec
    periods = spec.periods
    listed_first = False
    if not periods.report_dates:
        dates = _listed_dates(listing, queries[0], periods.count or 1)
        if not dates:
            return spec
        periods = periods.model_copy(update={"count": len(dates), "report_dates": dates})
        listed_first = True
    known = dict(periods.company_report_dates)
    if listed_first and spec.companies:
        known[queries[0].casefold()] = periods.report_dates
    for company in spec.companies:
        key = company.query.casefold()
        if key in known:
            continue
        try:
            dates = _listed_dates(listing, company.query, periods.count or 1)
        except SessionQuotaError:
            raise
        except Exception:
            # This company's cells report their own failure; it must not refuse
            # the whole window for the companies that do resolve.
            continue
        if dates:
            known[key] = dates
    periods = periods.model_copy(update={"company_report_dates": tuple(known.items())})
    if periods == spec.periods:
        return spec
    return spec.model_copy(update={"periods": periods})


def _named_dates(periods: Any, named: tuple[NamedPeriodSpec, ...]) -> tuple[date, ...]:
    matched = {
        day
        for spec in named
        for day in dates_for(tuple(periods), spec.year, spec.quarter, calendar=spec.calendar)
    }
    return tuple(sorted(matched, reverse=True))


def _materialize_named_periods(spec: AnalysisSpec, runtime: Runtime) -> AnalysisSpec:
    """Each company's own quarter ends for the named periods (ADR 0007).

    "Q3 FY2024" is Apple's quarter ended June 29 and Microsoft's ended March 31;
    each company's filings say which is which. A company without a filing for
    the period gets no cells, and the turn says so.
    """
    lister = getattr(runtime.facts, "fiscal_periods", None)
    if lister is None:
        return spec
    periods = spec.periods
    known = dict(periods.company_report_dates)
    for company in spec.companies:
        key = company.query.casefold()
        if key in known:
            continue
        try:
            listed = lister(company.query)
        except SessionQuotaError:
            raise
        except Exception:
            # This company's cells report their own failure.
            continue
        known[key] = _named_dates(listed, periods.named)
    first = next(
        (known[company.query.casefold()] for company in spec.companies
         if known.get(company.query.casefold())),
        (),
    )
    longest = max((len(dates) for dates in known.values()), default=0)
    updated = periods.model_copy(
        update={
            "report_dates": first,
            "count": longest or None,
            "company_report_dates": tuple(known.items()),
        }
    )
    if updated == periods:
        return spec
    return spec.model_copy(update={"periods": updated})


def is_filing_change_proposal(proposal: Any) -> bool:
    if isinstance(proposal, SpecPatch):
        return False
    intent = getattr(proposal, "intent", None)
    if intent == Intent.FILING_CHANGE:
        return True
    action = getattr(proposal, "action", None)
    return getattr(action, "intent", None) == Intent.FILING_CHANGE


def is_qualitative_proposal(proposal: Any) -> bool:
    if isinstance(proposal, SpecPatch):
        return False
    intent = getattr(proposal, "intent", None)
    return intent in QUALITATIVE_INTENTS


def is_structured_proposal(proposal: Any) -> bool:
    if isinstance(proposal, SpecPatch):
        return True
    intent = getattr(proposal, "intent", None)
    return intent in STRUCTURED_INTENTS


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


RANKED_LATEST_QUARTER_BANNER = (
    "Ranked lists show each company's latest quarter. "
    "Name the companies to see a multi-quarter window."
)
FISCAL_Q4_GAP_BANNER = (
    "This window skips fiscal fourth quarters: companies report them in the 10-K, "
    "not a 10-Q, so they have no standalone quarterly fact."
)
CALENDARS_DIFFER_BANNER = (
    "These companies' fiscal quarters end on different dates, "
    "so each row shows the company's own quarter."
)
TASK_FAILURE_MESSAGE = "This part of the analysis could not be completed. Please try again."


def _task_failure_result(task: CompiledTask, exc: BaseException) -> TurnResult:
    """Isolate an unexpected cell failure as a typed partial or refuse.

    A provider failure (an EDGAR outage, retries exhausted) is not evidence that
    the filing lacks the fact, so it gets its own reason. The raw exception text
    never reaches the visitor.
    """
    reason = SOURCE_UNAVAILABLE if isinstance(exc, ProviderError) else MISSING_FACT
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
                    reason=reason,
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
                    reason=reason,
                )
                for company in task.company_queries
            ],
        )
    return TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=TASK_FAILURE_MESSAGE,
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
            except SessionQuotaError:
                raise
            except Exception as exc:
                results.append(_task_failure_result(task, exc))
            if on_progress is not None:
                on_progress(index + 1, total)
        return results

    workers = min(max_workers, total)
    ordered: list[TurnResult | None] = [None] * total
    done = 0
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {
            pool.submit(
                copy_context().run,
                partial(execute_compiled_task, task, runtime, query=query),
            ): index
            for index, task in enumerate(tasks)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                ordered[index] = future.result()
            except SessionQuotaError:
                raise
            except Exception as exc:
                ordered[index] = _task_failure_result(tasks[index], exc)
            done += 1
            if on_progress is not None:
                on_progress(done, total)
    except BaseException:
        # A quota stop (or any escape) must not wait for the queued tasks to run.
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
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
    """The level a change row subtracts, with the facts it came from.

    A margin level keeps its formula inputs and a derived quarter its source
    facts, so the change's evidence shows every filing behind both levels.
    """
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
        derivation=row.derivation,
        derived_from=list(row.components) or list(row.derived_from),
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


# One fiscal quarter is 13 weeks, or 14 in a 53-week year; calendar quarters run
# 90 to 92 days. Anything outside this band pairs non-adjacent quarters.
_ADJACENT_QUARTER_GAP = (timedelta(days=84), timedelta(days=105))


def _adjacent_quarters(newer: date, older: date) -> bool:
    low, high = _ADJACENT_QUARTER_GAP
    return low <= newer - older <= high


def _yoy_prior(row: TableRow, ordered: list[TableRow]) -> TableRow | None:
    """The row a year earlier, allowing for 52/53-week fiscal calendars."""
    assert row.end_date is not None
    target = _yoy_prior_date(row.end_date)
    best: TableRow | None = None
    for candidate in ordered:
        if candidate is row or candidate.end_date is None:
            continue
        distance = abs(candidate.end_date - target)
        if distance > FISCAL_WEEK_TOLERANCE:
            continue
        if best is None or distance < abs((best.end_date or date.min) - target):
            best = candidate
    return best


def across_period_change_rows(
    levels: list[TableRow], *, sequential: bool = True
) -> list[TableRow]:
    """Sequential and year-over-year change from period-aligned level cells.

    ``sequential`` is off when the analyst asked for year-over-year change only.
    """
    by_key: dict[tuple[str, str], list[TableRow]] = {}
    for row in levels:
        if row.value is None or row.end_date is None or row.comparison is not None:
            continue
        by_key.setdefault((row.cik or row.company_name, row.metric), []).append(row)

    changes: list[TableRow] = []
    for group in by_key.values():
        ordered = sorted(group, key=lambda r: r.end_date or date.min, reverse=True)
        for newer, older in zip(ordered, ordered[1:], strict=False):
            assert newer.end_date is not None and older.end_date is not None
            # A missing quarter in the window must not turn into a two-quarter
            # change labelled "sequential".
            if sequential and _adjacent_quarters(newer.end_date, older.end_date):
                changes.append(_change_row(newer, older, comparison="sequential"))
        for row in ordered:
            prior = _yoy_prior(row, ordered)
            if prior is None:
                continue
            changes.append(_change_row(row, prior, comparison="yoy"))
    return changes


def merge_task_results(
    tasks: tuple[CompiledTask, ...],
    results: list[TurnResult],
    *,
    across_periods: bool = False,
    sequential: bool = True,
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
        rows = list(rows) + across_period_change_rows(rows, sequential=sequential)

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


def _order_by_metric(result: TurnResult, metric: str) -> TurnResult:
    """Order a ranking's market-cap members by ``metric``, largest first.

    Membership stays the snapshot's top N by market cap: ranking a whole
    industry by a filed metric would mean a lookup per company in it.
    """
    latest: dict[str, TableRow] = {}
    for row in result.table_rows:
        if row.metric != metric or row.comparison is not None or not row.cik:
            continue
        shown = latest.get(row.cik)
        if shown is None or (row.end_date or date.min) > (shown.end_date or date.min):
            latest[row.cik] = row
    ranks = {row.cik: row.rank for row in result.table_rows if row.cik and row.rank is not None}
    if not latest or not ranks:
        return result

    def key(cik: str) -> tuple[bool, Decimal, int]:
        row = latest.get(cik)
        value = row.value if row is not None else None
        return (value is None, -(value or Decimal(0)), ranks[cik] or 0)

    order = {cik: index for index, cik in enumerate(sorted(ranks, key=key), start=1)}
    rows = sorted(
        (
            row.model_copy(update={"rank": order[row.cik]}) if row.cik in order else row
            for row in result.table_rows
        ),
        key=lambda row: (row.rank is None, row.rank or 0),
    )
    return result.model_copy(update={"table_rows": rows, "ordered_by": metric})


def _fill_identity(result: TurnResult, spec: AnalysisSpec) -> TurnResult:
    """Give a failed cell the company's name and ticker, not the typed query.

    A cell that never reached a filing carries only the query ("walmart");
    the spec resolved that query to a snapshot company, so show that one.
    """
    known = {
        company.query.casefold(): company
        for company in spec.companies
        if company.cik and company.name
    }
    if not known or not any(not row.cik for row in result.table_rows):
        return result
    # The name the company's other cells already show, so one table names it once.
    shown = {row.cik: row.company_name for row in result.table_rows if row.cik}
    rows = [
        row.model_copy(
            update={
                "company_name": shown.get(match.cik, match.name),
                "ticker": match.ticker,
                "cik": match.cik,
            }
        )
        if not row.cik and (match := known.get(row.company_name.casefold())) is not None
        else row
        for row in result.table_rows
    ]
    return result.model_copy(update={"table_rows": rows})


def run_spec_turn_context(
    ctx: TurnContext, runtime: Runtime
) -> tuple[TurnResult, AnalysisSpec | None, SpecPatch]:
    """Apply a structured proposal: patch → resolve → validate → compile → execute."""
    message = ctx.message
    current_spec = ctx.current_spec
    proposal = ctx.proposal
    on_progress = ctx.on_progress
    max_workers = ctx.max_workers
    patch = (
        proposal
        if isinstance(proposal, SpecPatch)
        else plan_to_spec_patch(proposal)
    )
    intent = getattr(proposal, "intent", None) if not isinstance(proposal, SpecPatch) else None
    invalid = _INVALID_QUARTER.search(message)
    if invalid is not None:
        return (
            TurnResult(
                intent=intent or Intent.LOOKUP,
                tool_traces=[],
                renderer=RendererKind.REFUSE,
                message=(
                    f"There is no Q{invalid.group(1)}: a fiscal year has four quarters, "
                    "Q1 to Q4."
                ),
            ),
            current_spec,
            patch,
        )
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
    if spec.periods.kind == "named" and spec.companies and not spec.periods.report_dates:
        return (
            _rejection_result(
                SpecRejection(
                    code="empty_spec",
                    message=(
                        f"No filings found for {spec.periods.label}. Periods are fiscal "
                        "years as each company names them; filings older than about "
                        "ten years may not be available."
                    ),
                )
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
    merged = merge_task_results(
        tasks,
        results,
        across_periods=across,
        sequential="year_over_year" not in spec.operations,
    )
    merged = _fill_identity(merged, spec)
    if "order_by_metric" in spec.operations and spec.constituents is not None and spec.metrics:
        merged = _order_by_metric(merged, spec.metrics[0])
    # Planner notes first: a corrected company name explains the whole answer.
    planner_notes = [
        note for note in getattr(proposal, "notes", ()) or () if isinstance(note, str)
    ]
    notes = [
        *planner_notes,
        *_already_present_notes(patch, current_spec, spec),
        *_period_notes(message, spec),
        *_short_ranking_notes(spec),
        *_capped_ranking_notes(patch),
    ]
    if notes:
        merged = merged.model_copy(update={"banners": [*merged.banners, *notes]})
    return merged, spec, patch


_SPECIFIC_PERIOD = re.compile(
    r"\b(?:"
    r"q[1-4]\s*(?:fy\s*)?'?\d{2,4}"
    r"|[1-4]q\s*(?:fy\s*)?'?\d{2,4}"
    r"|(?:fy|fiscal(?:\s+year)?)\s*'?\d{2,4}"
    r"|(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?(?:fy\s*)?\d{4}"
    r"|(?:in|for|during)\s+(?:19|20)\d{2}"
    r")\b",
    re.IGNORECASE,
)


def _short_ranking_notes(spec: AnalysisSpec) -> list[str]:
    """Say so when an industry has fewer snapshot members than the ranking asked for."""
    ranked = spec.constituents
    if ranked is None or not ranked.members or len(ranked.members) >= ranked.limit:
        return []
    count = len(ranked.members)
    noun = "company" if count == 1 else "companies"
    return [
        f"The snapshot holds only {count} {noun} in {ranked.industry}, so this list "
        f"is shorter than the {ranked.limit} asked for."
    ]


def _capped_ranking_notes(patch: SpecPatch) -> list[str]:
    """Say so when a ranking asked for more companies than one lists."""
    if patch.ranked_request is None or patch.ranked_request[1] <= MAX_RANKED_COMPANIES:
        return []
    return [
        f"A ranking lists at most {MAX_RANKED_COMPANIES} companies, so this shows the "
        f"top {MAX_RANKED_COMPANIES} rather than {patch.ranked_request[1]}."
    ]


def _already_present_notes(
    patch: SpecPatch, current: AnalysisSpec | None, spec: AnalysisSpec
) -> list[str]:
    """Say so when an "add" names a company the analysis already has."""
    if current is None or patch.mode != "extend" or not patch.add_companies:
        return []
    before = {company.cik for company in current.companies if company.cik}
    if len(spec.companies) > len(current.companies):
        return []
    names = [
        short_name(company.name) or company.query
        for company in spec.companies
        if company.cik in before
        and any(
            token.casefold() in (company.query.casefold(), company.ticker.casefold())
            or token.casefold() in company.name.casefold()
            for token in patch.add_companies
        )
    ]
    if not names:
        return []
    return [f"{' and '.join(names)} {'is' if len(names) == 1 else 'are'} already in this analysis."]


def _possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def _short_date(day: date) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def _named_period_notes(spec: AnalysisSpec) -> list[str]:
    """Say which quarter ends a named fiscal period stands for, and who has none."""
    notes: list[str] = []
    periods = spec.periods
    own = dict(periods.company_report_dates)
    label = periods.label
    missing = [
        short_name(company.name) or company.query
        for company in spec.companies
        if not own.get(company.query.casefold())
    ]
    single = len(periods.named) == 1 and periods.named[0].quarter is not None
    dated = [company for company in spec.companies if own.get(company.query.casefold())]
    if single and not periods.named[0].calendar and len(dated) == 1:
        company = dated[0]
        notes.append(
            f"{_possessive(short_name(company.name) or company.query)} {label} ended "
            f"{_short_date(own[company.query.casefold()][0])}."
        )
    elif single and not periods.named[0].calendar and dated:
        ends = [
            f"{_possessive(short_name(company.name) or company.query)} ended "
            f"{_short_date(own[company.query.casefold()][0])}"
            for company in spec.companies
            if own.get(company.query.casefold())
        ]
        if ends:
            notes.append(
                f"{label} is each company's own fiscal quarter: " + "; ".join(ends) + "."
            )
    if missing and len(missing) < len(spec.companies):
        notes.append(f"No filing for {label} from {', '.join(missing)}.")
    return notes


def _period_notes(message: str, spec: AnalysisSpec) -> list[str]:
    """Say plainly when the window shown is not the one the analyst asked for."""
    notes: list[str] = []
    window = (
        f"the last {spec.periods.count} quarters"
        if spec.periods.kind == "last_n_quarters"
        else "the latest quarter"
    )
    named = _SPECIFIC_PERIOD.search(message)
    if named is not None and spec.periods.kind != "named":
        notes.append(
            f"I couldn't read “{named.group(0)}” as a period; this shows {window}. "
            "Try “Q3 2024” or “fiscal 2025”."
        )
    if spec.periods.kind == "last_n_quarters" and _TRAILING_YEAR.search(message):
        notes.append(TRAILING_YEAR_BANNER)
    if spec.periods.kind == "named":
        notes.extend(_named_period_notes(spec))
        if spec.constituents is not None:
            notes.append(RANKED_LATEST_QUARTER_BANNER)
        return notes
    if spec.constituents is not None and spec.periods.kind == "last_n_quarters":
        # compile_tasks does not expand ranked lists over a period window; say so
        # instead of showing a "Last N quarters" chip over one quarter of data.
        notes.append(RANKED_LATEST_QUARTER_BANNER)
    windows = [spec.periods.report_dates]
    if spec.periods.kind == "last_n_quarters" and spec.companies:
        groups = calendar_groups(spec)
        windows = [dates for _, dates in groups]
        if len(groups) > 1:
            notes.append(CALENDARS_DIFFER_BANNER)
    if any(
        not _adjacent_quarters(newer, older)
        for dates in windows
        for newer, older in zip(dates, dates[1:], strict=False)
    ):
        notes.append(FISCAL_Q4_GAP_BANNER)
    return notes


def run_spec_turn(
    message: str,
    runtime: Runtime,
    *,
    current_spec: AnalysisSpec | None,
    proposal: Any,
    on_progress: ProgressCallback | None = None,
    max_workers: int = DEFAULT_TASK_MAX_WORKERS,
) -> tuple[TurnResult, AnalysisSpec | None, SpecPatch]:
    """Compatibility wrapper: bundle args into TurnContext and delegate."""
    return run_spec_turn_context(
        TurnContext(
            message=message,
            current_spec=current_spec,
            proposal=proposal,
            on_progress=on_progress,
            max_workers=max_workers,
        ),
        runtime,
    )
