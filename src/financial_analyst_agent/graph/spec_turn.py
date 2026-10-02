"""Execute a compiled analysis-spec task through existing closed workflows."""

from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from contextvars import copy_context
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    DEFAULT_RANK_LIMIT,
    LOOKUP_FAILED,
    MISSING_FACT,
    NOT_OPERATING_COMPANY,
    QUALITATIVE_INTENTS,
    SNAPSHOT_METRICS,
    SOURCE_UNAVAILABLE,
    STRUCTURED_INTENTS,
    ComponentProvenance,
    Intent,
    RendererKind,
    Runtime,
    TableRow,
    ToolTrace,
    TurnResult,
    refuse_unknown_metric,
    unknown_metric_message,
)
from financial_analyst_agent.domain.errors import (
    SOURCE_FAILURES,
    CompanyNotFoundError,
    IneligibleIssuerError,
    ProviderError,
    ProviderRefusal,
    SessionQuotaError,
    UnknownIndustryError,
)
from financial_analyst_agent.graph.analysis_spec import (
    MAX_QUARTERS_ASKED,
    MAX_RANKED_COMPANIES,
    AnalysisSpec,
    CompiledTask,
    NamedPeriodSpec,
    PeriodSelection,
    ResolvedCompany,
    SpecDraft,
    SpecPatch,
    SpecRejection,
    apply_patch,
    calendar_groups,
    compile_tasks,
    emptied_by,
    resolve_spec,
    validate_spec,
)
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.providers.sec.client import sec_turn_seconds_left
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
from financial_analyst_agent.services.fiscal_periods import calendar_quarter, dates_for
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
_DROP_AND_ADD_EDIT = re.compile(
    r"^\s*(?:drop|remove)\s+(.+?)\s*,?\s+(?:and\s+)?(?:add|include|show)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_LAST_N_QUARTERS = re.compile(
    r"\blast\s+(\d+|two|three|four|five|six|eight)\s+quarters?\b",
    re.IGNORECASE,
)
_YOY = re.compile(
    r"\b(?:year[\s-]*over[\s-]*year|yoy|show yoy|compare to last year|(?:a|one) year ago"
    r"|(?:over|in) the (?:last|past) year|(?:from|since|vs\.?|versus) (?:a year ago|last year)"
    r"|grow(?:th|n|ing)?|grew|how (?:has|have|did) .+ change[d]?|trend(?:ing)?"
    r"|why did .+ (?:drop|fall|decline|rise|jump|increase|decrease|go (?:up|down)))\b",
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
    # A bare year is that fiscal year ("Apple revenue 2024", "2025 vs 2024"), but
    # "since 2020" is a window and "top 2000" a count.
    re.compile(
        r"(?<![\w$.,/-])(?<!since )(?<!top )(?<!last )(?P<y>(?:19|20)\d{2})(?![\w%.,/-])", re.I
    ),
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH = r"(?P<m>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
# "September quarter 2025", "December 2025 quarter", "quarter ended June 2026":
# the calendar quarter that month closes. Other months name no calendar quarter.
_MONTH_QUARTER_PATTERNS = (
    re.compile(
        rf"\b(?:quarter|period|three months)\s+(?:ended|ending|to)\s+(?:in\s+)?{_MONTH}\s+"
        rf"(?:\d{{1,2}},?\s+)?(?P<y>(?:19|20)\d{{2}})\b",
        re.I,
    ),
    re.compile(rf"\b{_MONTH}\s+(?P<y>(?:19|20)\d{{2}})\s+quarter\b", re.I),
    re.compile(rf"\b{_MONTH}\s+quarter\s+(?:of\s+)?(?P<y>(?:19|20)\d{{2}})\b", re.I),
)
# "from 2022 to 2024": each fiscal year in the range.
_YEAR_RANGE = re.compile(
    r"\b(?:from|between)\s+(?:fy\s*)?(?P<a>(?:19|20)\d{2})\s+(?:to|and|through|until|-)\s+"
    r"(?:fy\s*)?(?P<b>(?:19|20)\d{2})\b",
    re.I,
)
_MAX_RANGE_YEARS = 10
# "20 years ago" names that fiscal year; "a year ago" is a year-over-year change.
_YEARS_AGO = re.compile(r"\b(?P<n>\d{1,2})\s+years?\s+ago\b", re.I)
# "last 3 years": that many years of quarters.
_LAST_N_YEARS = re.compile(
    r"\b(?:last|past|previous|prior)\s+(\d+|two|three|four|five|six|eight|ten)\s+years\b", re.I
)
# "next quarter" asks for a forecast; filings only report what has happened.
_FORECAST = re.compile(
    r"\bnext\s+(?:quarter|year|fiscal\s+year|fy)\b|\bforecasts?\b|\bprojected\b|\bpredict",
    re.I,
)
# Wording that asks for year-over-year change only, not quarter-to-quarter too.
_EXPLICIT_YOY = re.compile(
    r"\b(?:year[\s-]*over[\s-]*year|yoy|(?:a|one) year (?:ago|earlier|before)"
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
_LATEST = re.compile(
    r"\b(?:latest|most recent|newest)\b|\b(?:last|this|current) quarter\b", re.IGNORECASE
)
_TRAILING_YEAR = re.compile(
    r"\b(?:ttm|ltm|trailing[\s-]+(?:twelve|12)[\s-]+months?|(?:last|past)\s+(?:twelve|12)\s+months)\b",
    re.I,
)
# "Apple revenue last year", "annual revenue": a year of quarters, like TTM.
_YEAR_OF_QUARTERS = re.compile(
    r"\b(?:last|past|previous|prior)\s+year\b|\bannual(?:ly)?\b|\byearly\b|\bfull[\s-]year\b",
    re.I,
)
YEAR_OF_QUARTERS_BANNER = (
    "The last year: these are the four latest quarters, shown one by one rather "
    "than summed."
)
_WHY_CHANGE = re.compile(r"^\s*why\b", re.I)
WHY_CHANGE_BANNER = (
    "Filings report what changed, not why: here is the change. Management explains "
    "the quarter in the 10-Q's MD&A, and “what changed in the latest 10-Q” shows it."
)
_YEAR_TO_DATE = re.compile(r"\b(?:ytd|year[\s-]+to[\s-]+date)\b", re.I)
# "since 2023": every quarter from the start of that year.
_SINCE_YEAR = re.compile(r"\bsince\s+(?:fy\s*|fiscal\s+(?:year\s+)?)?(?P<y>(?:19|20)\d{2})\b", re.I)
_MAX_SINCE_QUARTERS = 20
# "H1 2026", "first half of fiscal 2026": two named quarters.
_HALF_YEAR = re.compile(
    rf"\b{_CALENDAR_WORD}(?:h(?P<h>[12])|(?P<hw>first|second|1st|2nd)\s+half(?:\s+of)?)\s*"
    rf"{_FISCAL_WORD}{_YEAR}",
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
    "ten": 10,
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
    metric = plan.metric if isinstance(getattr(plan, "metric", None), str) else None
    metrics = (metric,) if metric else ()
    if intent is Intent.LOOKUP:
        # A question naming no company names none: "the" or "unknown" is not one.
        company = plan.company if plan.company and plan.company != "unknown" else None
        return SpecPatch(
            mode="replace", add_companies=(company,) if company else (), add_metrics=metrics
        )
    if intent is Intent.COMPARE:
        ordered = getattr(plan, "order_by_metric", False) is True
        return SpecPatch(
            mode="replace",
            add_companies=tuple(plan.companies),
            add_metrics=metrics,
            add_operations=(
                ("across_companies", "order_by_metric") if ordered else ("across_companies",)
            ),
        )
    if intent not in (Intent.RANK, Intent.RANK_AND_LOOKUP):
        raise ValueError(f"cannot lift intent to spec patch: {intent!r}")
    ranked = (
        plan.industry or "",
        int(getattr(plan, "limit", DEFAULT_RANK_LIMIT) or DEFAULT_RANK_LIMIT),
    )
    if intent is Intent.RANK:
        return SpecPatch(mode="replace", ranked_request=ranked)
    ordered = getattr(plan, "order_by_metric", False) is True
    return SpecPatch(
        mode="replace",
        ranked_request=ranked,
        add_metrics=metrics,
        add_operations=("rank", "order_by_metric") if ordered else ("rank",),
    )


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


def implied_metrics(message: str, *, short: bool = True) -> tuple[str, ...]:
    """Metrics a question implies when it names none ("Which is bigger?").

    ``short`` lets a message of a few words ("Nvidia") ask for the overview; a
    question naming a word the catalog lacks ("Apple turnover") turns it off.
    """
    if _BIGGER.search(message):
        return ("market_cap", "revenue")
    if _PROFITABLE.search(message):
        return ("net_income", "net_margin")
    if _GROWING.search(message):
        return ("revenue",)
    if _OVERVIEW.search(message) or (short and len(message.split()) <= _OVERVIEW_MAX_WORDS):
        return OVERVIEW_METRICS
    return ()


def _names_companies(patch: SpecPatch) -> bool:
    return (
        patch.ranked_request is None
        and bool(patch.add_companies)
        and all(company and company != "unknown" for company in patch.add_companies)
    )


def _names_new_subject(patch: SpecPatch, spec: AnalysisSpec, message: str = "") -> bool:
    """Whether the patch names a company or ranking the current analysis lacks.

    A model planner often repeats the current company in a follow-up's plan, so
    naming a company already on screen is not a new question. Naming only some
    of the companies on screen, in the analyst's own words ("Walmart revenue
    over the last four quarters" after Costco and Walmart), is one.
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
    if any(company.casefold() not in known for company in patch.add_companies):
        return True
    return patch.mode == "replace" and _narrows_to_named(patch, spec, message)


def _narrows_to_named(patch: SpecPatch, spec: AnalysisSpec, message: str) -> bool:
    """Whether the analyst named fewer of the companies on screen than are shown."""
    wanted = {company.casefold() for company in patch.add_companies}
    kept = [
        company
        for company in spec.companies
        if wanted & {company.query.casefold(), company.name.casefold(), company.ticker.casefold()}
    ]
    if not kept or len(kept) >= len(spec.companies):
        return False
    words = f" {normalize_words(message)} "
    return all(
        f" {normalize_words(short_name(company.name))} " in words
        or f" {company.ticker.casefold()} " in words
        for company in kept
        if company.name or company.ticker
    )


def normalize_words(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", text.casefold()).split())


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
            clarify_kind="ambiguous_metric",
        )
    phrased = resolved.unique_metrics
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
    # The planner names a word the catalog lacks ("turnover"): refuse with it
    # rather than answer a short question with the overview.
    unknown_word = any(
        metric not in ALLOWED_METRICS and metric not in ("unknown", OVERVIEW_PLAN)
        for metric in patch.add_metrics
    )
    implied = (
        implied_metrics(message, short=not unknown_word)
        if _names_companies(patch) and not guessed
        else ()
    )
    if not implied and _names_companies(patch) and OVERVIEW_PLAN in patch.add_metrics:
        implied = OVERVIEW_METRICS
    if implied:
        return patch.model_copy(update={"add_metrics": implied}), None
    if patch.ranked_request is not None and not patch.add_metrics:
        return patch, None
    # Replace-mode metric question with an unknown phrase: refuse with the full catalog
    # even when the planner guessed a catalog slug.
    term = "unknown"
    if patch.add_metrics:
        candidate = patch.add_metrics[0]
        if candidate not in ALLOWED_METRICS:
            term = candidate
    return patch, refuse_unknown_metric(effective_intent, term)


def _unique_metrics_from_phrase(text: str) -> tuple[str, ...]:
    return resolve_metric_phrase(text).unique_metrics


def _companies_named_in(companies: tuple[str, ...], text: str) -> tuple[str, ...]:
    """The planner's companies that ``text`` names in so many words."""
    words = f" {normalize_words(text)} "
    return tuple(
        company for company in companies if f" {normalize_words(company)} " in words
    )


def _company_tokens(text: str) -> tuple[str, ...]:
    parts = re.split(r"\s+and\s+|,\s*", text, flags=re.IGNORECASE)
    return tuple(part.strip(" .,") for part in parts if part.strip(" .,"))


def _quarters_asked(raw: str) -> int:
    """The window "last N quarters" names, kept between one and ``MAX_QUARTERS_ASKED``."""
    raw = raw.casefold()
    if raw in _NUMBER_WORDS:
        return _NUMBER_WORDS[raw]
    digits = raw.lstrip("0")
    if not digits.isdigit():
        return 1 if raw.isdigit() else 4
    if len(digits) > len(str(MAX_QUARTERS_ASKED)):
        return MAX_QUARTERS_ASKED
    return min(int(digits), MAX_QUARTERS_ASKED)


def parse_named_periods(message: str) -> tuple[NamedPeriodSpec, ...]:
    """Every period the message names, in the order named, without repeats."""
    found: list[tuple[int, NamedPeriodSpec]] = []
    taken: list[tuple[int, int]] = []
    for match in _HALF_YEAR.finditer(message):
        start, end = match.span()
        if any(start < other_end and end > other_start for other_start, other_end in taken):
            continue
        groups = match.groupdict()
        raw_year = groups["y"]
        year = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
        second = groups.get("h") == "2" or (groups.get("hw") or "").casefold() in ("second", "2nd")
        first_quarter = 3 if second else 1
        taken.append((start, end))
        for offset in (0, 1):
            found.append(
                (
                    start + offset,
                    NamedPeriodSpec(
                        year=year, quarter=first_quarter + offset, calendar=bool(groups.get("cal"))
                    ),
                )
            )
    def free(start: int, end: int) -> bool:
        return not any(start < other_end and end > other_start for other_start, other_end in taken)

    for match in _YEAR_RANGE.finditer(message):
        first, last = sorted((int(match.group("a")), int(match.group("b"))))
        if free(*match.span()) and last - first < _MAX_RANGE_YEARS:
            taken.append(match.span())
            found.extend(
                (match.start() + offset, NamedPeriodSpec(year=year))
                for offset, year in enumerate(range(last, first - 1, -1))
            )
    for pattern in _MONTH_QUARTER_PATTERNS:
        for match in pattern.finditer(message):
            month = _MONTHS[match.group("m")[:3].casefold()]
            if not free(*match.span()):
                continue
            taken.append(match.span())
            if month % 3:
                # April closes no calendar quarter; the turn says it was not read.
                continue
            period = NamedPeriodSpec(year=int(match.group("y")), quarter=month // 3, calendar=True)
            found.append((match.start(), period))
    for match in _YEARS_AGO.finditer(message):
        if int(match.group("n")) >= 2 and free(*match.span()):
            taken.append(match.span())
            found.append(
                (match.start(), NamedPeriodSpec(year=date.today().year - int(match.group("n"))))
            )
    for pattern in _NAMED_PERIOD_PATTERNS:
        for match in pattern.finditer(message):
            start, end = match.span()
            if not free(start, end):
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


def _window_asked(message: str) -> int | None:
    """The quarters "last N quarters" or "last N years" asks for, or None."""
    quarters = _LAST_N_QUARTERS.search(message)
    if quarters is not None:
        return _quarters_asked(quarters.group(1))
    years = _LAST_N_YEARS.search(message)
    if years is not None:
        return min(4 * _quarters_asked(years.group(1)), MAX_QUARTERS_ASKED)
    return None


def _since_quarters(since: re.Match[str]) -> int:
    """Quarters from the start of the year "since 2020" names to today."""
    today = date.today()
    return max(1, (today.year - int(since.group("y"))) * 4 + (today.month + 2) // 3)


def bind_periods_from_message(patch: SpecPatch, message: str) -> SpecPatch:
    """Period windows come from the analyst's wording, not a model slug."""
    asked = _window_asked(message)
    yoy = _YOY.search(message) is not None
    # "quarter over quarter" is a window of sequential changes.
    sequential = _SEQUENTIAL.search(message) is not None
    named = parse_named_periods(message)
    since = _SINCE_YEAR.search(message)
    if not named and asked is None and not yoy and since is not None:
        count = min(_since_quarters(since), _MAX_SINCE_QUARTERS)
        return patch.model_copy(
            update={"set_periods": PeriodSelection(kind="last_n_quarters", count=count)}
        )
    if not named and asked is None and not yoy and (
        _TRAILING_YEAR.search(message) or _YEAR_OF_QUARTERS.search(message)
    ):
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
    if asked is None and not yoy and not sequential:
        if _LATEST.search(message) is not None:
            # "latest" after a year-over-year window: one quarter, no change chip.
            return patch.model_copy(
                update={
                    "set_periods": PeriodSelection(),
                    "remove_operations": (
                        *patch.remove_operations,
                        "across_periods",
                        "year_over_year",
                    ),
                }
            )
        return patch
    operations = patch.add_operations
    if (yoy or sequential) and "across_periods" not in operations:
        operations = (*operations, "across_periods")
    explicit_yoy = _EXPLICIT_YOY.search(message) is not None and not sequential
    if explicit_yoy and "year_over_year" not in operations:
        operations = (*operations, "year_over_year")
    if asked is None and patch.set_periods is not None:
        return patch.model_copy(update={"add_operations": operations})
    count = asked if asked is not None else 5
    if (yoy or sequential) and count < 5:
        count = 5
    if explicit_yoy:
        # Each of the N quarters needs the one a year before it.
        count = _YOY_WINDOW if asked is None else min(asked + 4, MAX_QUARTERS_ASKED)
    return patch.model_copy(
        update={
            "set_periods": PeriodSelection(kind="last_n_quarters", count=count),
            "add_operations": operations,
        }
    )


def _extend(patch: SpecPatch, **fields: Any) -> SpecPatch:
    """The patch as an edit of the current analysis rather than a new ranking."""
    return patch.model_copy(update={"mode": "extend", "ranked_request": None, **fields})


def _swap_pair(message: str) -> tuple[str, str] | None:
    """(incoming, outgoing) of "use X instead of Y" or "remove Y add X"."""
    swapped = _SWAP_EDIT.match(message)
    if swapped is not None:
        return swapped.group(1).strip(), swapped.group(2).strip()
    # "remove revenue add net income" is a swap, not the removal of both.
    both = _DROP_AND_ADD_EDIT.match(message)
    if both is not None:
        return both.group(2).strip(" .,"), both.group(1).strip(" .,")
    return None


def refine_patch_from_message(
    patch: SpecPatch,
    message: str,
    current_spec: AnalysisSpec | None,
) -> SpecPatch:
    """Turn follow-up wording into an extend patch when the planner still replaced."""
    patch = bind_periods_from_message(patch, message)
    if current_spec is None:
        return patch

    swap = _swap_pair(message.strip())
    if swap is not None:
        incoming, outgoing = swap
        add_metrics = _unique_metrics_from_phrase(incoming)
        remove_metrics = _unique_metrics_from_phrase(outgoing)
        if add_metrics and remove_metrics:
            return _extend(
                patch,
                add_metrics=add_metrics,
                remove_metrics=remove_metrics,
                add_companies=(),
                remove_companies=(),
            )
        return _extend(
            patch,
            add_companies=(incoming,),
            remove_companies=(outgoing,),
            add_metrics=(),
        )

    added = _ADD_EDIT.match(message.strip())
    if added is not None:
        token = added.group(1).strip(" .,")
        metrics = _unique_metrics_from_phrase(token)
        # "add Google margin" adds Google as well as the margin.
        named = _companies_named_in(patch.add_companies, token)
        if metrics:
            return _extend(patch, add_metrics=metrics, add_companies=named)
        resolved = resolve_metric_phrase(token)
        if resolved.kind == "ambiguous":
            return _extend(patch, add_companies=named)
        if patch.add_metrics and not patch.add_companies:
            return _extend(patch, add_companies=())
        companies = _company_tokens(token)
        return _extend(patch, add_companies=companies, add_metrics=())

    dropped = _DROP_EDIT.match(message.strip())
    if dropped is not None:
        token = dropped.group(1).strip(" .,")
        metrics = _unique_metrics_from_phrase(token)
        if metrics:
            return _extend(patch, remove_metrics=metrics, add_metrics=(), add_companies=())
        resolved = resolve_metric_phrase(token)
        if resolved.kind == "ambiguous":
            return _extend(patch, add_companies=(), remove_companies=(), add_metrics=())
        companies = _company_tokens(token)
        if re.fullmatch(r"(?:both|them|all|all of them|everything|every company)", token, re.I):
            # "remove both": every company on screen, which the turn then says it cannot.
            companies = tuple(company.query for company in current_spec.companies)
        return _extend(patch, remove_companies=companies, add_metrics=(), add_companies=())

    compare_to = _COMPARE_TO_ISSUER.match(message.strip())
    if compare_to is not None and _YOY.search(message) is None:
        token = compare_to.group(1).strip(" .,")
        if token and not _unique_metrics_from_phrase(token):
            return _extend(patch, add_companies=(token,), add_metrics=())

    # "What was it last quarter?" names nothing new: it is not a question of its own.
    standalone = (patch.ranked_request is not None or _names_companies(patch)) and (
        _STANDALONE_LOOKUP.search(message.strip()) is not None
        or _STANDALONE_COMPARE.search(message.strip()) is not None
    )
    # A period on its own ("for Q3 2024", "last 8 quarters") edits the current
    # analysis. One that names another company or ranking ("Microsoft TTM net
    # income") is a new question and keeps what it names.
    period_only = not _names_new_subject(patch, current_spec, message)
    if patch.set_periods is not None and patch.mode == "replace" and not standalone and period_only:
        return _extend(patch, add_companies=(), add_metrics=())
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
    return tuple(listing(company, limit=count))


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


def drop_annual_filers(spec: AnalysisSpec, runtime: Runtime) -> tuple[AnalysisSpec, list[str]]:
    """Leave out named companies that file annual 20-F/40-F reports instead of 10-Qs.

    A foreign private issuer such as Novo Nordisk has no quarterly facts, so
    every cell would read "Missing fact"; the turn says why instead.
    """
    checker = getattr(runtime.facts, "files_quarterly", None)
    if checker is None or not spec.companies:
        return spec, []
    kept: list[Any] = []
    dropped: list[str] = []
    for company in spec.companies:
        try:
            quarterly, name = checker(company.ticker or company.query)
        except SessionQuotaError:
            raise
        except Exception:
            # Resolution problems surface through the company's own cells.
            kept.append(company)
            continue
        if quarterly:
            kept.append(company)
        else:
            dropped.append(short_name(company.name if company.cik else name) or company.query)
    if not dropped:
        return spec, []
    return spec.model_copy(update={"companies": tuple(kept)}), dropped


def annual_filer_note(names: list[str]) -> str:
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    verb = "files" if len(names) == 1 else "file"
    return (
        f"{listed} {verb} annual reports with the SEC (Form 20-F or 40-F) rather than "
        "quarterly 10-Qs, so there are no quarterly figures to show."
    )


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


def _draft_intent(draft: SpecDraft) -> Intent:
    """The closed intent a draft's shape asks for, when no planned intent came with it."""
    if draft.ranked_request is not None:
        return Intent.RANK_AND_LOOKUP if draft.metrics else Intent.RANK
    return Intent.COMPARE if len(draft.company_queries) > 1 else Intent.LOOKUP


def _rejection_result(rejection: SpecRejection, intent: Intent) -> TurnResult:
    return TurnResult(
        intent=intent,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=rejection.message,
    )


def execute_compiled_task(
    task: CompiledTask, runtime: Runtime, *, query: str = ""
) -> TurnResult:
    from financial_analyst_agent.graph import run_workflow_turn

    # CompiledTask kinds are Intent values; rank tasks carry no metric or period.
    plan = SimpleNamespace(
        intent=Intent(task.kind),
        company=task.company_queries[0] if task.kind == "lookup" else None,
        companies=list(task.company_queries) if task.kind == "compare" else [],
        metric=task.metric,
        industry=task.industry,
        limit=task.limit or DEFAULT_RANK_LIMIT,
        topic=None,
        report_date=task.report_date,
    )
    return run_workflow_turn(plan, runtime, query=query)


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
SOURCE_UNAVAILABLE_MESSAGE = (
    "SEC EDGAR could not be reached just now, so this could not be answered. "
    "Please try again in a few minutes."
)
# How long the tasks may run past the turn's SEC budget: parsing what was read.
_TASK_GRACE_SECONDS = 15.0


def _missing_cell(
    company: str, metric: str, report_date: date | None, reason: str = MISSING_FACT
) -> TableRow:
    return TableRow(
        company_name=company,
        ticker="",
        cik="",
        metric=metric,
        end_date=report_date,
        reason=reason,
    )


def _task_failure_result(task: CompiledTask, exc: BaseException) -> TurnResult:
    """Isolate an unexpected cell failure as a typed partial or refuse.

    Neither a source failure (an EDGAR outage, retries exhausted, a full disk)
    nor a fault of ours is evidence that the filing lacks the fact, so each
    gets its own reason. The raw exception text never reaches the visitor.
    """
    reason = SOURCE_UNAVAILABLE if isinstance(exc, SOURCE_FAILURES) else LOOKUP_FAILED
    if task.kind in ("lookup", "compare") and task.company_queries and task.metric:
        companies = task.company_queries[:1] if task.kind == "lookup" else task.company_queries
        return TurnResult(
            intent=Intent(task.kind),
            tool_traces=[],
            renderer=RendererKind.TABLE,
            table_rows=[
                _missing_cell(company, task.metric, task.report_date, reason)
                for company in companies
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
        left = sec_turn_seconds_left()
        timeout = None if left == float("inf") else max(0.0, left) + _TASK_GRACE_SECONDS
        try:
            for future in as_completed(futures, timeout=timeout):
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
        except FuturesTimeout:
            # The turn's time is up: what is still running answers as unavailable.
            late = ProviderError("The turn's time for SEC requests is spent")
            for index, result in enumerate(ordered):
                if result is None:
                    ordered[index] = _task_failure_result(tasks[index], late)
            pool.shutdown(wait=False, cancel_futures=True)
            return [result for result in ordered if result is not None]
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
    # A fund in a window of quarters says so, as it does in a comparison (ADR 0002).
    codes = {
        trace.provenance.get("error", {}).get("code")
        for trace in result.tool_traces
        if isinstance(trace.provenance.get("error"), dict)
    }
    reason = NOT_OPERATING_COMPANY if IneligibleIssuerError.code in codes else MISSING_FACT
    return [_missing_cell(task.company_queries[0], task.metric, task.report_date, reason)]


def _subtracted_level_provenance(row: TableRow) -> ComponentProvenance:
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
        components=[_subtracted_level_provenance(prior), _subtracted_level_provenance(current)],
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
# Up to 17 weeks: some 52/53-week retailers (Costco) run a 16- or 17-week fourth quarter.
_ADJACENT_QUARTER_GAP = (timedelta(days=84), timedelta(days=126))


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


def _order_companies_by_metric(result: TurnResult, metric: str) -> TurnResult:
    """Order named companies by their latest ``metric``, largest first ("sort by revenue")."""
    latest: dict[str, TableRow] = {}
    for row in result.table_rows:
        if row.metric != metric or row.comparison is not None or row.value is None:
            continue
        key = row.cik or row.company_name
        shown = latest.get(key)
        if shown is None or (row.end_date or date.min) > (shown.end_date or date.min):
            latest[key] = row
    if not latest:
        return result
    first_seen = list(dict.fromkeys(row.cik or row.company_name for row in result.table_rows))

    def order(company: str) -> tuple[bool, Decimal, int]:
        row = latest.get(company)
        value = row.value if row is not None else None
        return (value is None, -(value or Decimal(0)), first_seen.index(company))

    ranking = {company: index for index, company in enumerate(sorted(first_seen, key=order))}
    rows = sorted(result.table_rows, key=lambda row: ranking[row.cik or row.company_name])
    return result.model_copy(update={"table_rows": rows})


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
    forecast = _FORECAST.search(message)
    if forecast is not None:
        return _refusal(intent, forecast_message(forecast.group(0))), current_spec, patch
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
                    clarify_kind="ambiguous_mode",
                ),
                current_spec,
                patch,
            )
    patch, early = bind_metrics_from_message(patch, message, intent=intent)
    if early is not None:
        return early, current_spec, patch
    emptied = emptied_by(current_spec, patch)
    if emptied is not None:
        return _refusal(intent, EMPTIED_MESSAGES[emptied]), current_spec, patch

    draft = apply_patch(current_spec, patch)
    # A refusal names the analysis that was asked for, not a default lookup.
    asked = intent or _draft_intent(draft)
    # Drop model-supplied metrics that are not in the catalog when wording did not
    # resolve a unique phrase (plan slug may still be present on replace).
    if draft.metrics and any(m not in ALLOWED_METRICS for m in draft.metrics):
        bad = next(m for m in draft.metrics if m not in ALLOWED_METRICS)
        return (
            _rejection_result(
                SpecRejection(
                    code="invalid_metric",
                    message=unknown_metric_message(bad),
                ),
                asked,
            ),
            None,
            patch,
        )

    try:
        spec = resolve_spec(draft, ranking=runtime.ranking)
    except UnknownIndustryError as exc:
        return (
            TurnResult(
                intent=asked,
                tool_traces=[],
                renderer=RendererKind.REFUSE,
                message=str(exc),
            ),
            None,
            patch,
        )
    if not spec.companies and spec.constituents is None and spec.metrics:
        # "what was the revenue?": naming the company next ("for Apple") completes it.
        held = current_spec if current_spec is not None else spec
        return _refusal(asked, no_company_message(spec.metrics)), held, patch
    outcome = validate_spec(spec)
    if outcome is not None:
        return _rejection_result(outcome, asked), None, patch

    spec, annual_filers = drop_annual_filers(spec, runtime)
    if annual_filers and not spec.companies and spec.constituents is None:
        return (
            _rejection_result(
                SpecRejection(code="empty_spec", message=annual_filer_note(annual_filers)),
                asked,
            ),
            None,
            patch,
        )

    try:
        spec = materialize_period_dates(spec, runtime)
    except (CompanyNotFoundError, *SOURCE_FAILURES) as exc:
        public = isinstance(exc, (CompanyNotFoundError, ProviderRefusal))
        return (
            TurnResult(
                intent=asked,
                tool_traces=[],
                renderer=RendererKind.REFUSE,
                message=str(exc) if public else SOURCE_UNAVAILABLE_MESSAGE,
            ),
            None,
            patch,
        )
    if spec.periods.kind == "named" and spec.companies and not spec.periods.report_dates:
        future = all(
            period.year > date.today().year for period in spec.periods.named
        ) or _after_latest_filing(spec, runtime)
        return (
            _rejection_result(
                SpecRejection(
                    code="empty_spec",
                    message=(
                        f"No filings found for {spec.periods.label}: it has not been "
                        "reported yet."
                        if future
                        else f"No filings found for {spec.periods.label}. Periods are fiscal "
                        "years as each company names them; filings older than about "
                        "ten years may not be available."
                    ),
                ),
                asked,
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
                ),
                asked,
            ),
            None,
            patch,
        )
    tasks = compile_tasks(spec)
    if not tasks:
        return (
            _rejection_result(
                SpecRejection(code="empty_spec", message="Analysis compiled to no tasks"),
                asked,
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
    if len(spec.companies) == 1 and spec.constituents is None:
        # "How is SPY doing?": one reason, said once, not a row for each metric.
        merged = _not_operating_once(merged, results, spec.companies[0])
    merged = _fill_identity(merged, spec)
    if "order_by_metric" in spec.operations and spec.constituents is not None and spec.metrics:
        merged = _order_by_metric(merged, _ordering_metric(spec, message))
    elif "order_by_metric" in spec.operations and spec.companies and spec.metrics:
        merged = _order_companies_by_metric(merged, _ordering_metric(spec, message))
    trend = overview_trend(spec, runtime, query=message, max_workers=max_workers)
    if trend is not None:
        merged = merged.model_copy(
            update={
                "trend_rows": trend.table_rows,
                "tool_traces": [*merged.tool_traces, *trend.tool_traces],
            }
        )
    # Planner notes first: a corrected company name explains the whole answer.
    planner_notes = [
        note for note in getattr(proposal, "notes", ()) or () if isinstance(note, str)
    ]
    notes = [
        *([annual_filer_note(annual_filers)] if annual_filers else []),
        *_already_present_notes(patch, current_spec, spec),
        *_period_notes(message, spec),
        *_short_ranking_notes(spec),
        *_capped_ranking_notes(patch),
    ]
    banners = list(dict.fromkeys([*planner_notes, *merged.banners, *notes]))
    if banners != merged.banners:
        merged = merged.model_copy(update={"banners": banners})
    resolved = _identity_from_rows(spec, merged)
    return merged, _with_market_date(resolved, runtime), patch


EMPTIED_MESSAGES = {
    "companies": (
        "That would remove the only company in this analysis. Name another to look at "
        "instead, for example “what about Microsoft?”, or start over."
    ),
    "metrics": (
        "That would leave no metric to show. Name one to show instead, for example "
        "“just net income”, or start over."
    ),
}


def forecast_message(asked: str) -> str:
    return (
        f"Filings report quarters that have already happened, so I can't forecast "
        f"“{asked}”. Try “last 4 quarters” to see the trend so far."
    )


def no_company_message(metrics: tuple[str, ...]) -> str:
    from financial_analyst_agent.presentation import format_field_name

    label = format_field_name(metrics[0])
    label = label if label[1:2].isupper() else label[:1].lower() + label[1:]
    return (
        f"I couldn't tell which company you mean. Name one or its ticker, for example "
        f"“Apple {label}”, or rank an industry, such as “top 5 banks by {label}”."
    )


def _refusal(intent: Intent | None, message: str) -> TurnResult:
    return TurnResult(
        intent=intent or Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=message,
    )


def _not_operating_once(
    merged: TurnResult, results: list[TurnResult], company: ResolvedCompany
) -> TurnResult:
    """One refusal where every cell of one company failed for the same reason.

    "How is SPY doing?" is a fund, not five "Not an operating company" rows.
    """
    rows = merged.table_rows
    reasons = {row.reason for row in rows}
    if not rows or any(row.value is not None for row in rows) or len(reasons) != 1:
        return merged
    said = next(
        (
            result.message
            for result in results
            if result.renderer is RendererKind.REFUSE and result.message
        ),
        None,
    )
    if said is None and reasons == {NOT_OPERATING_COMPANY}:
        name = short_name(company.name) or company.query
        said = (
            f"{name} is not an operating company (it is a fund, business development "
            "company or similar listing), so its 10-Q figures are outside what this "
            "analyst covers."
        )
    if said is None:
        return merged
    return TurnResult(
        intent=merged.intent,
        tool_traces=merged.tool_traces,
        renderer=RendererKind.REFUSE,
        message=said,
    )


def _ordering_metric(spec: AnalysisSpec, message: str) -> str:
    """The metric to order by: named here, chosen by "sort by", else the first."""
    named = [metric for metric in _unique_metrics_from_phrase(message) if metric in spec.metrics]
    if named:
        return named[0]
    if spec.order_by in spec.metrics:
        return str(spec.order_by)
    return spec.metrics[0]


def _with_market_date(spec: AnalysisSpec, runtime: Runtime) -> AnalysisSpec:
    """Date an analysis of snapshot figures only (market cap, price) by its snapshot."""
    market_only = all(metric in SNAPSHOT_METRICS for metric in spec.metrics)
    as_of = None
    if market_only and (spec.metrics or spec.constituents is not None):
        reader = getattr(runtime.ranking, "snapshot_as_of", None)
        try:
            as_of = date.fromisoformat(str(reader())[:10]) if callable(reader) else None
        except ValueError:
            as_of = None
    return spec if spec.as_of == as_of else spec.model_copy(update={"as_of": as_of})


def _after_latest_filing(spec: AnalysisSpec, runtime: Runtime) -> bool:
    """Whether every named period ends after the first company's newest filed quarter."""
    lister = getattr(runtime.facts, "fiscal_periods", None)
    if lister is None or not spec.companies:
        return False
    try:
        listed = tuple(lister(spec.companies[0].query))
    except SessionQuotaError:
        raise
    except Exception:
        return False
    if not listed:
        return False
    latest = max(listed, key=lambda period: period.end)
    for named in spec.periods.named:
        if named.calendar:
            last = calendar_quarter(latest.end)
        elif latest.fiscal_year is None or latest.quarter is None:
            return False
        else:
            last = (latest.fiscal_year, latest.quarter)
        if (named.year, named.quarter or 1) <= last:
            return False
    return True


# One company's overview carries a few quarters of these beside its table.
TREND_METRICS: tuple[str, ...] = ("revenue", "net_margin")
TREND_QUARTERS = 5


def overview_trend(
    spec: AnalysisSpec,
    runtime: Runtime,
    *,
    query: str = "",
    max_workers: int = DEFAULT_TASK_MAX_WORKERS,
) -> TurnResult | None:
    """The last few quarters of revenue and net margin for "How is Nvidia doing?".

    Only the overview of one company at its latest quarter gets them: the small
    trend charts above its table. The rows read the same filings the table does;
    a lookup that fails or runs out of the thread's allowance leaves the charts
    out and the answer as it was.
    """
    if (
        len(spec.companies) != 1
        or spec.constituents is not None
        or spec.operations
        or spec.periods.kind != "latest_quarter"
        or spec.metrics != OVERVIEW_METRICS
    ):
        return None
    window = spec.model_copy(
        update={
            "metrics": TREND_METRICS,
            "periods": PeriodSelection(kind="last_n_quarters", count=TREND_QUARTERS),
        }
    )
    try:
        window = materialize_period_dates(window, runtime)
        tasks = compile_tasks(window)
        results = dispatch_compiled_tasks(tasks, runtime, query=query, max_workers=max_workers)
    except (CompanyNotFoundError, SessionQuotaError, *SOURCE_FAILURES):
        return None
    if not tasks:
        return None
    merged = merge_task_results(tasks, results, across_periods=False)
    levels = [row for row in merged.table_rows if row.comparison is None and row.value is not None]
    return merged.model_copy(update={"table_rows": levels})


def _identity_from_rows(spec: AnalysisSpec, result: TurnResult) -> AnalysisSpec:
    """Name a company the snapshot lacks as its filings do (Tesla → TSLA).

    The recorded demo holds filings for companies outside its ranking snapshot;
    the spec keeps only the typed query for those until a filing names them.
    """
    if all(company.ticker for company in spec.companies):
        return spec
    filed = [row for row in result.table_rows if row.ticker and row.cik]
    companies = []
    for company in spec.companies:
        match = None
        if not company.ticker:
            query = company.query.casefold()
            match = next(
                (
                    row
                    for row in filed
                    if row.ticker.casefold() == query
                    or re.match(rf"{re.escape(query)}\b", row.company_name.casefold())
                ),
                None,
            )
        companies.append(
            company
            if match is None
            else company.model_copy(
                update={"cik": match.cik, "ticker": match.ticker, "name": match.company_name}
            )
        )
    return spec.model_copy(update={"companies": tuple(companies)})


# Periods shorter than a quarter, which no 10-Q reports on its own.
_SUB_QUARTER = re.compile(
    r"\b(?:last|this|past|previous)\s+(?:month|week)\b|\byesterday\b"
    r"|\b(?:in|for|during)\s+(?:january|february|march|april|june|july|august|september"
    r"|october|november|december)\b(?!\s+(?:19|20)\d{2})",
    re.IGNORECASE,
)
_SPECIFIC_PERIOD = re.compile(
    r"\b(?:"
    r"q[1-4]\s*(?:fy\s*)?'?\d{2,4}"
    r"|[1-4]q\s*(?:fy\s*)?'?\d{2,4}"
    r"|(?:fy|fiscal(?:\s+year)?)\s*'?\d{2,4}"
    r"|(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?(?:fy\s*)?\d{4}"
    r"|(?:in|for|during)\s+(?:19|20)\d{2}"
    # "quarter ended April 2026": a month this parser does not read as a quarter.
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2},?\s+)?"
    r"(?:19|20)\d{2}"
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
    elif (
        spec.periods.kind == "last_n_quarters"
        and _YEAR_OF_QUARTERS.search(message)
        and not _YOY.search(message)
    ):
        notes.append(YEAR_OF_QUARTERS_BANNER)
    if spec.periods.kind != "named" and _SUB_QUARTER.search(message):
        notes.append(f"Filings report quarters, not months or weeks, so this shows {window}.")
    if _WHY_CHANGE.search(message):
        notes.append(WHY_CHANGE_BANNER)
    if _YEAR_TO_DATE.search(message):
        notes.append(
            f"Year-to-date totals aren't supported yet, so this shows {window}. "
            "Try “last 4 quarters”."
        )
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
    if spec.periods.kind == "last_n_quarters":
        notes.extend(_window_notes(message, windows))
    return notes


def _window_notes(message: str, windows: list[tuple[date, ...]]) -> list[str]:
    """Say when a window is shorter than asked: capped, or more than the filings hold."""
    notes: list[str] = []
    wanted = _window_asked(message)
    typed = _LAST_N_QUARTERS.search(message)
    since = _SINCE_YEAR.search(message)
    if typed is not None and typed.group(1).isdigit() and int(typed.group(1)) > MAX_QUARTERS_ASKED:
        notes.append(
            f"A window shows at most {MAX_QUARTERS_ASKED} quarters, so this asks for "
            f"{MAX_QUARTERS_ASKED} rather than {int(typed.group(1))}."
        )
    elif wanted is None and since is not None:
        quarters = _since_quarters(since)
        wanted = min(quarters, _MAX_SINCE_QUARTERS)
        if quarters > _MAX_SINCE_QUARTERS:
            notes.append(
                f"Quarters since {since.group('y')} number {quarters}; a window shows at most "
                f"{_MAX_SINCE_QUARTERS}, so this asks for the latest {_MAX_SINCE_QUARTERS}."
            )
    shown = max((len(dates) for dates in windows), default=0)
    if wanted is not None and 0 < shown < wanted:
        notes.append(f"The filings here hold only {shown} of the {wanted} quarters asked for.")
    return notes
