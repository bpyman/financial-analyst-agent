from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from financial_analyst_agent.contracts import PER_SHARE_METRICS
from financial_analyst_agent.evidence_store import THREAD_EVIDENCE_BANNER
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.services.fact_selector import (
    FOURTH_QUARTER_LABEL,
    YEAR_TO_DATE_LABEL,
)
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
from financial_analyst_agent.services.fiscal_periods import GROSS_PROFIT_LABEL
from financial_analyst_agent.turn import (
    ALLOWED_METRICS,
    EXPLORATORY_RESEARCH_BANNER,
    FORMULA_METRICS,
    MODEL_ANALYSIS_BANNER,
    PERCENT_FORMULAS,
    REPORTED_METRICS,
    SNAPSHOT_METRICS,
    Intent,
    RendererKind,
    TableRow,
    TurnResult,
)

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_TRILLION = Decimal("1000000000000")
_BILLION = Decimal("1000000000")
_MILLION = Decimal("1000000")
_CENTS = Decimal("0.01")
_TENTH = Decimal("0.1")

_REASON_LABELS = {
    "missing_fact": "Missing fact",
    "period_mismatch": "Period mismatch",
    "ambiguous_concept": "Ambiguous concept",
    "zero_denominator": "Zero denominator",
    "source_unavailable": "Source unavailable",
    "not_reported_for_quarter": "Reported for the year only",
}
_FIELD_LABELS = {
    "comparison": "Change",
    "cik": "CIK",
    "source_url": "Source URL",
    "company_name": "Company",
    "accession_number": "Accession number",
    "start_date": "Start date",
    "end_date": "End date",
    "market_cap": "Market cap",
    "cost_of_revenue": "Cost of revenue",
    "gross_profit": "Gross profit",
    "operating_expenses": "Operating expenses",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "research_and_development": "Research and development",
    "selling_general_and_administrative": "Selling, general and administrative",
    "interest_expense": "Interest expense",
    "income_tax_expense": "Income tax expense",
    "pretax_income": "Pretax income",
    "gross_margin": "Gross margin",
    "operating_margin": "Operating margin",
    "net_margin": "Net margin",
    "rd_to_sales": "R&D to sales",
    "sga_ratio": "SG&A ratio",
    "effective_tax_rate": "Effective tax rate",
    "interest_coverage": "Interest coverage",
    "eps_diluted": "Diluted EPS",
    "eps_basic": "Basic EPS",
    "operating_cash_flow": "Operating cash flow",
    "capital_expenditure": "Capital expenditure",
    "free_cash_flow": "Free cash flow",
}
# Marks a derived value in a table cell; a banner says how it was derived.
DERIVED_MARK = " †"
_DERIVED_NOTES = {
    FOURTH_QUARTER_LABEL: (
        "a fiscal fourth quarter is the 10-K's full year minus the 10-Q's nine months"
    ),
    YEAR_TO_DATE_LABEL: (
        "a cash-flow quarter is the 10-Q's year to date minus the previous quarter's"
    ),
    GROSS_PROFIT_LABEL: "gross profit is revenue minus cost of revenue",
}


def format_usd(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    amount = abs(value)
    if amount == 0:
        return "$0"
    units = ((_TRILLION, "T"), (_BILLION, "B"), (_MILLION, "M"))
    for index, (unit, suffix) in enumerate(units):
        if amount < unit:
            continue
        scaled = (amount / unit).quantize(_CENTS, rounding=ROUND_HALF_UP)
        if scaled >= 1000 and index > 0:
            # Rounding reached the next unit: $999,996,000 is "$1.00 B", not "$1000.00 M".
            unit, suffix = units[index - 1]
            scaled = (amount / unit).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return f"{sign}${scaled:.2f} {suffix}"
    grouped = f"{int(amount):,}"
    return f"{sign}${grouped}"


def format_percent(ratio: Decimal) -> str:
    percent = (ratio * Decimal("100")).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f"{percent:.1f}%"


def format_per_share(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value).quantize(_CENTS, rounding=ROUND_HALF_UP):.2f}"


def format_multiple(ratio: Decimal) -> str:
    scaled = ratio.quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f"{scaled:.1f}x"


def format_date(value: date) -> str:
    return f"{_MONTHS[value.month - 1]} {value.day}, {value.year}"


def format_datetime_utc(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    utc = aware.astimezone(UTC)
    hour12 = utc.hour % 12 or 12
    suffix = "AM" if utc.hour < 12 else "PM"
    return f"{format_date(utc.date())}, {hour12}:{utc.minute:02d} {suffix} UTC"


def _humanize_field(key: str) -> str:
    label = _FIELD_LABELS.get(key)
    if label is None:
        return " ".join(part.capitalize() for part in key.split("_"))
    return label


def format_field_name(key: str) -> str:
    return _humanize_field(key)


def format_reason(reason: str) -> str:
    label = _REASON_LABELS.get(reason)
    if label is None:
        label = " ".join(reason.split("_")).capitalize()
    return label


def format_metric_value(metric: str, value: Decimal | None) -> str:
    if value is None:
        return ""
    if metric == "interest_coverage":
        return format_multiple(value)
    if metric in PERCENT_FORMULAS:
        return format_percent(value)
    if metric in PER_SHARE_METRICS:
        return format_per_share(value)
    return format_usd(value)


def derived_banner(rows: list[TableRow]) -> str:
    """One line on how the table's derived values were computed, or ""."""
    labels: list[str] = []
    for row in rows:
        if row.value is None:
            continue
        for label in [row.derivation, *(component.derivation for component in row.components)]:
            if label and label not in labels:
                labels.append(label)
    if not labels:
        return ""
    notes = [_DERIVED_NOTES.get(label, label) for label in labels]
    return (
        "† Derived from reported figures because the filings do not report it on its own: "
        + "; ".join(notes)
        + ". Both source facts are in the evidence."
    )


# A 13-week quarter is 91 days; a 14-week one 98. Anything longer is a long quarter.
_LONG_QUARTER_DAYS = 98


def long_quarter_banner(rows: list[TableRow]) -> str:
    """Say which quarters run longer than about 13 weeks (Costco's 16-week Q4), or ""."""
    long: dict[str, list[tuple[date, int]]] = {}
    for row in rows:
        if row.value is None or row.start_date is None or row.end_date is None:
            continue
        days = (row.end_date - row.start_date).days + 1
        if days > _LONG_QUARTER_DAYS:
            name = short_name(row.company_name) or row.company_name
            if (row.end_date, days) not in long.get(name, []):
                long.setdefault(name, []).append((row.end_date, days))
    notes: list[str] = []
    for name, quarters in long.items():
        weeks = " or ".join(str(week) for week in sorted({round(days / 7) for _, days in quarters}))
        ends = _join_words([format_date(end) for end, _ in quarters])
        plural = "quarters" if len(quarters) > 1 else "quarter"
        owner = f"{name}'" if name.endswith("s") else f"{name}'s"
        notes.append(f"{owner} {plural} ended {ends} ran {weeks} weeks")
    if not notes:
        return ""
    return "; ".join(notes) + ", longer than the usual 13 weeks, which lifts those amounts."


def newer_filing_banner(rows: list[TableRow]) -> str:
    """Say which companies' newest filed quarter SEC's structured data still lacks, or ""."""
    pending: dict[str, date] = {}
    for row in rows:
        if row.value is not None and row.newer_filing_end is not None:
            name = short_name(row.company_name) or row.ticker
            pending.setdefault(name, row.newer_filing_end)
    if not pending:
        return ""
    if len(pending) == 1:
        ((name, end),) = pending.items()
        return (
            f"SEC's structured data does not yet include {name}'s filing for the quarter "
            f"ended {_date(end)}, so {name} is shown for the newest quarter SEC has."
        )
    filings = [f"{name} (quarter ended {_date(end)})" for name, end in pending.items()]
    return (
        "SEC's structured data does not yet include the newest filings from "
        f"{_join_words(filings)}, so those companies are shown for the newest quarter SEC has."
    )


def _date(day: date) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def is_derived(row: TableRow) -> bool:
    """A derived quarter, or a value computed from one (ADR 0007)."""
    return bool(row.derivation) or any(component.derivation for component in row.components)


_TOOL_HEADERS = {
    "get_financials": "Looked up {what} in SEC filings",
    "compare_metrics": "Compared {what} in SEC filings",
    "rank_companies": "Ranked {what} in the universe snapshot",
    "filing_change": "Compared 10-Q text for {what}",
    "search_news": "Searched news for {what}",
    "explain_topic": "Wrote a qualitative summary of {what}",
}


def _as_iso_date(raw: object) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _trace_period(trace: Any) -> str:
    provenance = getattr(trace, "provenance", None) or {}
    start = _as_iso_date(provenance.get("start_date"))
    end = _as_iso_date(provenance.get("end_date"))
    labeled = _period_label(start, end)
    if labeled:
        return labeled
    args = getattr(trace, "args", None) or {}
    report = _as_iso_date(args.get("report_date"))
    if report is None:
        return ""
    return format_date(report)


def format_chart_amount(metric: str, value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return ""
    if not amount.is_finite():
        return ""
    return format_metric_value(metric, amount)


def chart_value_kind(metric: str) -> str:
    if metric == "interest_coverage":
        return "multiple"
    if metric in PERCENT_FORMULAS:
        return "percent"
    if metric in PER_SHARE_METRICS:
        return "per_share"
    return "usd"


def try_parse_datetime(raw: str) -> datetime | None:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


_TABLE_KEYS = (
    "rank",
    "company_name",
    "ticker",
    "cik",
    "metric",
    "comparison",
    "value",
    "currency",
    "start_date",
    "end_date",
    "form",
    "accession_number",
    "taxonomy",
    "concept",
    "source_url",
    "reason",
)
# A ranking stays narrow: no CIK, currency, or taxonomy. Rank-and-lookup rows
# keep their filing provenance so each ranked fact links to its 10-Q.
_RANK_TABLE_KEYS = (
    "rank",
    "company_name",
    "ticker",
    "value",
    "start_date",
    "end_date",
    "form",
    "accession_number",
    "concept",
    "source_url",
    "reason",
)
# A change row sits in the same value column as the levels it is derived from, so
# it must say what it is and carry an explicit sign.
_COMPARISON_LABELS = {
    "yoy": "Year over year",
    "sequential": "Quarter over quarter",
}
_LEVEL_LABEL = "Reported"
_SNAPSHOT_PREFIX = "Universe snapshot as of "
# Banner codes a qualitative turn carries, in the words the window shows.
_BANNER_COPY = {
    THREAD_EVIDENCE_BANNER: "Figures fetched earlier in this conversation were reused.",
    MODEL_ANALYSIS_BANNER: (
        "Model analysis — written by the model, not quoted from a filing. "
        "It may only repeat numbers the tools returned."
    ),
    EXPLORATORY_RESEARCH_BANNER: (
        "Exploratory research — a read-only brief from the cited sources. "
        "It reports no financial facts or computed values."
    ),
}
_METRIC_CLARIFY_PROMPT = "Which metric do you mean?"
_SCOPE_CLARIFY_PROMPT = "Add to the current analysis, or start a new one?"
_SCOPE_CANDIDATES = ("extend", "replace")


@dataclass(frozen=True)
class QuarterlyFactCard:
    company_name: str
    ticker: str
    metric_header: str
    amount: str
    period_label: str
    form: str
    accession_number: str
    concept: str
    source_url: str


@dataclass(frozen=True)
class DisplayTable:
    headers: tuple[str, ...]
    keys: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    numbers: tuple[tuple[int | float | None, ...], ...] = ()


@dataclass(frozen=True)
class DisplayTrace:
    header: str
    inputs: tuple[tuple[str, str], ...]
    outputs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DisplayCitation:
    index: int
    title: str
    url: str
    published: str | None


@dataclass(frozen=True)
class Presentation:
    intent: str
    banners: tuple[str, ...]
    traces: tuple[DisplayTrace, ...]
    citations: tuple[DisplayCitation, ...]
    fact_card: QuarterlyFactCard | None
    table: DisplayTable | None
    essay: str | None
    message: str | None
    candidates: tuple[str, ...]
    intent_label: str = ""
    chart: ChartSpec | None = None
    evidence: tuple[EvidenceItem, ...] = ()
    disclosures: tuple[DisplayDisclosure, ...] = ()
    # The question a clarification asks; set only when candidates are offered.
    clarify_prompt: str | None = None
    # Next questions the window offers as one-tap chips.
    suggestions: tuple[str, ...] = ()
    # "info" for a guide reply, "warning" for a refusal.
    message_tone: str = "warning"


def metric_legend() -> tuple[str, ...]:
    return tuple(_humanize_field(metric) for metric in ALLOWED_METRICS)


def metric_groups() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        (
            "Reported (SEC EDGAR)",
            tuple(_humanize_field(metric) for metric in REPORTED_METRICS),
        ),
        ("Calculated", tuple(_humanize_field(metric) for metric in FORMULA_METRICS)),
        (
            "Daily snapshot (FMP)",
            tuple(_humanize_field(metric) for metric in SNAPSHOT_METRICS),
        ),
    )


_INTENT_LABELS = {
    "lookup": "Quarterly lookup",
    "compare": "Comparison",
    "rank": "Industry ranking",
    "rank_and_lookup": "Rank and lookup",
    "explain": "Qualitative analysis",
    "news_and_explain": "Current events",
    "exploratory_research": "Exploratory research",
    "filing_change": "Filing change",
}

_LATEST_QUARTER_RULE = "Latest standalone quarterly 10-Q; no year-to-date derivation."
_SNAPSHOT_RULE = "Universe snapshot market cap; not a 10-Q filing fact."
_FORMULA_RULE = "Calculated from the listed component facts; no LLM arithmetic."
_MIXED_PERIOD_CAPTION = "Latest standalone quarter; periods differ by issuer."


@dataclass(frozen=True)
class ChartSpec:
    """A chart plus every piece of text it shows, so no client formats a number.

    ``value_kind`` picks the axis tick style and ``metric_label`` titles the axis.
    Trend lines also carry ``period_labels`` (one per record), ``series`` (the
    company keys of each record), and ``amounts`` (each record's values as the
    table formats them), so tooltips read the same strings as the table.
    """

    kind: str
    title: str
    records: tuple[dict[str, object], ...]
    metric: str = ""
    caption: str = ""
    horizontal: bool = False
    value_kind: str = "usd"
    metric_label: str = ""
    period_labels: tuple[str, ...] = ()
    series: tuple[str, ...] = ()
    amounts: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class EvidenceItem:
    label: str
    amount: str
    raw_amount: str
    company_name: str
    ticker: str
    cik: str
    concept: str
    period_label: str
    accession_number: str
    form: str
    source_url: str
    selection_rule: str


@dataclass(frozen=True)
class DisplayDisclosure:
    section_label: str
    change_kind: str
    before_text: str
    after_text: str
    older_accession: str
    newer_accession: str
    older_url: str
    newer_url: str


def intent_label(intent: str) -> str:
    return _INTENT_LABELS.get(intent, _humanize_field(intent))


def spec_chips(spec: Any) -> tuple[str, ...]:
    """Compact labels for the active analysis spec."""
    chips: list[str] = []
    companies = getattr(spec, "companies", ())
    for company in companies:
        chips.append(company.ticker or company.name)
    constituents = getattr(spec, "constituents", None)
    if constituents is not None:
        chips.append(f"{constituents.industry} top {constituents.limit}")
    for metric in getattr(spec, "metrics", ()):
        chips.append(_humanize_field(str(metric)))
    periods = getattr(spec, "periods", None)
    if periods is not None:
        kind = getattr(periods, "kind", "")
        if kind == "last_n_quarters":
            chips.append(f"Last {periods.count} quarters")
        elif kind == "named":
            chips.append(getattr(periods, "label", "") or "Named period")
        else:
            chips.append("Latest quarter")
    for operation in getattr(spec, "operations", ()):
        chips.append(_humanize_field(str(operation)))
    return tuple(chips)


def _fiscal_week_buckets(ends: set[date]) -> dict[date, date]:
    """Map each period end to the latest end within a fiscal week of it.

    Apple's March 28 and Microsoft's March 31 are one quarter on the chart, not
    two points a few days apart.
    """
    buckets: dict[date, date] = {}
    cluster: list[date] = []
    for end in sorted(ends):
        if cluster and end - cluster[0] > FISCAL_WEEK_TOLERANCE:
            buckets.update(dict.fromkeys(cluster, cluster[-1]))
            cluster = []
        cluster.append(end)
    buckets.update(dict.fromkeys(cluster, cluster[-1]))
    return buckets


def _chart_spec(result: TurnResult, table: DisplayTable | None) -> ChartSpec | None:
    comparison_free = [
        row for row in result.table_rows if row.comparison is None
    ]
    rank_cross_section = result.intent in (Intent.RANK, Intent.RANK_AND_LOOKUP)
    rows = (
        comparison_free
        if rank_cross_section
        else [row for row in comparison_free if row.value is not None]
    )
    if table is None or len(rows) < 2:
        return None
    if len({row.metric for row in rows}) > 1:
        return None
    companies = {row.company_name for row in rows}
    periods_by_company: dict[str, set[date]] = {}
    for row in rows:
        if row.end_date is None:
            continue
        periods_by_company.setdefault(row.company_name, set()).add(row.end_date)
    if not rank_cross_section and any(
        len(periods) >= 2 for periods in periods_by_company.values()
    ):
        # Valued rows decide whether a trend is worth drawing; every dated row
        # keeps its quarter, so a missing one is a gap, not a skipped period.
        series_companies = {row.company_name for row in rows}
        dated = [
            row
            for row in comparison_free
            if row.end_date is not None
            and row.metric == rows[0].metric
            and row.company_name in series_companies
        ]
        buckets = _fiscal_week_buckets({row.end_date for row in dated if row.end_date})
        merged: dict[date, dict[str, object]] = {}
        for row in dated:
            if row.end_date is None:
                continue
            period = buckets[row.end_date]
            bucket = merged.setdefault(period, {"Period": period.isoformat()})
            bucket[row.company_name] = (
                float(row.value) if row.value is not None else None
            )
        metric = rows[0].metric
        periods = sorted(merged)
        records = tuple(merged[period] for period in periods)
        return ChartSpec(
            kind="line",
            title="Trend",
            records=records,
            metric=metric,
            value_kind=chart_value_kind(metric),
            metric_label=_humanize_field(metric),
            period_labels=tuple(format_date(period) for period in periods),
            series=tuple(dict.fromkeys(row.company_name for row in rows)),
            amounts=tuple(
                {
                    key: format_chart_amount(metric, value)
                    for key, value in record.items()
                    if key != "Period"
                }
                for record in records
            ),
        )
    if len(companies) >= 2:
        ends = {row.end_date for row in rows if row.end_date is not None}
        mixed_periods = len(ends) >= 2
        metric = rows[0].metric
        return ChartSpec(
            kind="bar",
            title="Comparison",
            records=tuple(
                _bar_record(row, ranked=rank_cross_section) for row in rows
            ),
            metric=metric,
            caption=_bar_caption(
                ranked=rank_cross_section,
                metric=metric,
                mixed_periods=mixed_periods,
                ordered_by=result.ordered_by,
            ),
            horizontal=rank_cross_section,
            value_kind=chart_value_kind(metric),
            metric_label=_humanize_field(metric),
        )
    return None


def _bar_record(row: TableRow, *, ranked: bool) -> dict[str, object]:
    ticker = row.ticker or row.company_name
    name = f"#{row.rank} {ticker}" if ranked and row.rank is not None else ticker
    missing = row.value is None
    amount = "" if missing else format_chart_amount(row.metric, row.value)
    reason = str(row.reason or "")
    label = amount if not missing else _REASON_LABELS.get(reason, reason or "Missing")
    record: dict[str, object] = {
        "Company": name,
        "Value": float(row.value) if row.value is not None else 0.0,
        "Amount": amount,
        "Label": label,
        "Missing": missing,
    }
    period = _period_label(row.start_date, row.end_date)
    if period:
        record["Period"] = period
    return record


def _bar_caption(
    *, ranked: bool, metric: str, mixed_periods: bool, ordered_by: str | None = None
) -> str:
    if ranked and metric != "market_cap":
        order = (
            f"Ordered by {_humanize_field(ordered_by).lower()} among the largest by market cap"
            if ordered_by
            else "Ordered by market cap"
        )
        caption = f"{order}; bar length is latest-quarter {_humanize_field(metric)}."
        if mixed_periods:
            return f"{caption} Periods differ by issuer."
        return caption
    if mixed_periods:
        return _MIXED_PERIOD_CAPTION
    return ""


def _period_label(start: date | None, end: date | None) -> str:
    if start is not None and end is not None:
        return f"{format_date(start)} – {format_date(end)}"
    if end is not None:
        return format_date(end)
    return ""


def _selection_rule(row: TableRow) -> str:
    if row.metric in SNAPSHOT_METRICS:
        return _SNAPSHOT_RULE
    if row.derivation:
        return f"Derived quarter: {row.derivation}. Both reported facts are listed."
    if row.components:
        return _FORMULA_RULE
    if row.comparison == "yoy":
        return "Year-over-year change from two standalone periods."
    if row.comparison == "sequential":
        return "Sequential change from two standalone periods."
    if row.form:
        return (
            f"Standalone {row.form} fact for the stated period; "
            "no year-to-date derivation."
        )
    return _LATEST_QUARTER_RULE


def _evidence_item(row: TableRow) -> EvidenceItem:
    amount = (
        format_metric_value(row.metric, row.value)
        if row.value is not None
        else (row.reason or "")
    )
    raw = str(row.value) if row.value is not None else ""
    period = _period_label(row.start_date, row.end_date)
    concept = row.concept or ""
    form = row.form or ""
    accession_number = row.accession_number or ""
    source_url = row.source_url or ""
    if row.components and not concept:
        concept = " / ".join(component.concept for component in row.components)
        first = row.components[0]
        form = form or first.form
        accession_number = accession_number or first.accession_number
        source_url = source_url or first.source_url
    change = _COMPARISON_LABELS.get(row.comparison or "")
    metric_label = _humanize_field(row.metric) + (f" · {change.lower()} change" if change else "")
    return EvidenceItem(
        label=f"{row.company_name} · {metric_label}" + (f" · {period}" if period else ""),
        amount=amount,
        raw_amount=raw,
        company_name=row.company_name,
        ticker=row.ticker,
        cik=row.cik,
        concept=concept,
        period_label=period,
        accession_number=accession_number,
        form=form,
        source_url=source_url,
        selection_rule=_selection_rule(row),
    )


def _component_rule(component: Any) -> str:
    derivation = getattr(component, "derivation", None)
    if derivation:
        return f"Derived quarter: {derivation}. Both reported facts are listed."
    if (component.end_date - component.start_date).days > 110:
        return f"Reported {component.form} amount for the stated period."
    return (
        f"Standalone {component.form} component fact for the stated period; "
        "no year-to-date derivation."
    )


def _evidence_from_component(row: TableRow, component: Any) -> EvidenceItem:
    period = _period_label(component.start_date, component.end_date)
    return EvidenceItem(
        label=(
            f"{row.company_name} · {_humanize_field(component.metric)}"
            + (f" · {period}" if period else "")
        ),
        amount=format_metric_value(component.metric, component.value),
        raw_amount=str(component.value),
        company_name=row.company_name,
        ticker=row.ticker,
        cik=row.cik,
        concept=component.concept,
        period_label=period,
        accession_number=component.accession_number,
        form=component.form,
        source_url=component.source_url,
        selection_rule=_component_rule(component),
    )


def _evidence_items(row: TableRow) -> tuple[EvidenceItem, ...]:
    items = [_evidence_item(row)]
    items.extend(_evidence_from_component(row, part) for part in _sources(row.derived_from))
    items.extend(_evidence_from_component(row, part) for part in _sources(row.components))
    return tuple(items)


def _sources(components: Any) -> list[Any]:
    """Each component, then the facts it came from, however deep (a margin's
    fiscal-Q4 revenue lists its 10-K and 10-Q)."""
    flat: list[Any] = []
    for component in components:
        flat.append(component)
        flat.extend(_sources(component.derived_from))
    return flat


def _dedupe_evidence(items: Any) -> tuple[EvidenceItem, ...]:
    """One inspector entry per fact: change rows repeat the levels they compare."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[EvidenceItem] = []
    for item in items:
        key = (item.label, item.raw_amount, item.accession_number)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


GUIDE_LABEL = "Guide"
REFUSED_LABEL = "Not answered"


def present_turn(result: TurnResult) -> Presentation:
    fact_card = None
    table = None
    if (
        result.intent is Intent.LOOKUP
        and result.renderer is RendererKind.TABLE
        and len(result.table_rows) == 1
        and result.table_rows[0].value is not None
        and result.table_rows[0].start_date is not None
        and result.table_rows[0].end_date is not None
    ):
        fact_card = _fact_card(result.table_rows[0])
    elif result.renderer is RendererKind.TABLE and result.table_rows:
        table = _display_table(result.table_rows, intent=result.intent)
    evidence = _dedupe_evidence(
        item
        for row in result.table_rows
        if row.cik or row.source_url or row.components
        for item in _evidence_items(row)
    )
    disclosures = tuple(
        DisplayDisclosure(
            section_label=item.section_label,
            change_kind=item.change_kind,
            before_text=item.before_text,
            after_text=item.after_text,
            older_accession=item.older_accession,
            newer_accession=item.newer_accession,
            older_url=item.older_url,
            newer_url=item.newer_url,
        )
        for item in result.disclosure_changes
    )
    banners = [_format_banner(banner) for banner in result.banners]
    derived = derived_banner(result.table_rows)
    if derived:
        banners.append(derived)
    long_quarters = long_quarter_banner(result.table_rows)
    if long_quarters:
        banners.append(long_quarters)
    newer = newer_filing_banner(result.table_rows)
    if newer:
        banners.append(newer)
    if result.ordered_by:
        label = _humanize_field(result.ordered_by).lower()
        banners.append(
            f"Ordered by {label}. The companies are the largest by market cap in "
            f"the snapshot, which holds market cap only, so a smaller company with more "
            f"{label} is not listed."
        )
    return Presentation(
        intent=result.intent.value,
        intent_label=(
            GUIDE_LABEL
            if result.guide
            else REFUSED_LABEL
            if result.renderer is RendererKind.REFUSE
            else intent_label(result.intent.value)
        ),
        banners=tuple(banners),
        traces=tuple(
            _display_trace(trace, names=_names_by_cik(result.table_rows))
            for trace in result.tool_traces
        ),
        citations=tuple(
            _display_citation(index, hit) for index, hit in enumerate(result.citations, start=1)
        ),
        fact_card=fact_card,
        table=table,
        chart=_chart_spec(result, table),
        evidence=evidence,
        disclosures=disclosures,
        essay=result.essay,
        message=(
            _friendly_message(result.message)
            if result.renderer is not RendererKind.CLARIFY
            else None
        ),
        candidates=tuple(_humanize_field(name) for name in result.candidates),
        clarify_prompt=_clarify_prompt(result),
        suggestions=tuple(result.suggestions),
        message_tone="info" if result.guide else "warning",
    )


_UNKNOWN_METRIC = re.compile(r"^Unknown metric '(?P<term>[^']*)'\. Allowed: .*$", re.DOTALL)
_UNKNOWN_INDUSTRY = re.compile(r"^Unknown industry '(?P<industry>.*)'\. Allowed: (?P<allowed>.*)$")
_COMPANY_NOT_FOUND = re.compile(r"^Company not found for query '(?P<query>.*)'$")
_METRIC_EXAMPLES = "revenue, net income, R&D, or operating margin"
_FRIENDLY_MESSAGES = {
    "No recorded filing document": (
        "The recorded demo holds 10-Q text only for the companies it recorded, and "
        "this filing is not among them. With live data, any company's 10-Qs can be compared."
    ),
    "Analysis has no companies or ranked constituents": (
        "I couldn't tell which company you mean. Name a company or ticker, "
        "for example “What was Apple's revenue?”"
    ),
    "No 10-Q or 10-Q/A filing found": (
        "This company has no 10-Q filings. Foreign private issuers file 20-F and "
        "6-K reports instead, which this app does not read yet."
    ),
    "Per-share figures for this quarter are reported only for a longer period": (
        "Filings report per-share figures such as EPS for a fiscal fourth quarter "
        "only inside the full-year total, and EPS cannot be subtracted the way "
        "revenue can, so there is no fourth-quarter figure to show."
    ),
    "No reported or derivable quarter exists for metric": (
        "This company's filings do not report that metric for this quarter. Not every "
        "company reports every line item: banks, for example, report neither revenue "
        "nor capital spending the way operating companies do."
    ),
    "No directly reported standalone-quarter fact exists for metric": (
        "This company's 10-Q does not report a standalone quarterly value for that "
        "metric. Not every company reports every line item: banks, for example, "
        "report neither revenue nor capital spending the way operating companies do."
    ),
}


def _friendly_message(message: str | None) -> str | None:
    """Put the domain's refusal text in the window's words.

    Domain messages name catalog slugs and internal terms (the MCP server and
    tests read them as they are); the audience window should not.
    """
    if message is None:
        return None
    if message in _FRIENDLY_MESSAGES:
        return _FRIENDLY_MESSAGES[message]
    unknown = _UNKNOWN_METRIC.match(message)
    if unknown is not None:
        term = unknown.group("term")
        if term in ("", "unknown"):
            return (
                "I couldn't find a metric I can look up in that question. I answer "
                f"from SEC 10-Q facts such as {_METRIC_EXAMPLES}, for example "
                "“What was Microsoft's latest quarterly revenue?”"
            )
        supported = ", ".join(_humanize_field(name) for name in ALLOWED_METRICS)
        return f"“{term}” is not a metric I can look up yet. Supported metrics: {supported}."
    industry = _UNKNOWN_INDUSTRY.match(message)
    if industry is not None:
        # Aliases ("finance") are lower case; the snapshot's sectors are titled.
        sectors = [name for name in industry.group("allowed").split(", ") if name[:1].isupper()]
        covers = f" It covers {_join_words(sectors)} companies." if sectors else ""
        return (
            f"I couldn't find “{industry.group('industry')}” companies in this snapshot."
            f"{covers} You can also name an industry within those, such as "
            "semiconductors, software, pharma or banks."
        )
    missing = _COMPANY_NOT_FOUND.match(message)
    if missing is not None and missing.group("query").strip().casefold() in ("", "unknown"):
        return (
            "I couldn't tell which company you mean. Name it or use its ticker, "
            "for example “Apple revenue” or “AAPL revenue”."
        )
    if missing is not None:
        return (
            f"I couldn't find a company called “{missing.group('query')}” in the "
            "filings available here. Check the spelling, or try the ticker."
        )
    return message


def _clarify_prompt(result: TurnResult) -> str | None:
    if result.renderer is not RendererKind.CLARIFY or not result.candidates:
        return None
    if tuple(result.candidates) == _SCOPE_CANDIDATES:
        return _SCOPE_CLARIFY_PROMPT
    return _METRIC_CLARIFY_PROMPT


def _fact_card(row: TableRow) -> QuarterlyFactCard:
    assert row.start_date is not None
    assert row.end_date is not None
    form = row.form or ""
    accession_number = row.accession_number or ""
    concept = row.concept or ""
    source_url = row.source_url or ""
    if row.components and not concept:
        concept = " / ".join(component.concept for component in row.components)
        first = row.components[0]
        form = form or first.form
        accession_number = accession_number or first.accession_number
        source_url = source_url or first.source_url
    lead = "Derived †" if is_derived(row) else "Standalone quarter"
    return QuarterlyFactCard(
        company_name=row.company_name,
        ticker=row.ticker,
        metric_header=_humanize_field(row.metric),
        amount=format_metric_value(row.metric, row.value),
        period_label=f"{lead} · {format_date(row.start_date)} – {format_date(row.end_date)}",
        form=form,
        accession_number=accession_number,
        concept=concept,
        source_url=source_url,
    )


def _cell_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _numeric_cell(row: TableRow, key: str) -> int | float | None:
    if key == "rank":
        return row.rank
    if key == "value" and row.value is not None:
        return float(row.value)
    return None


WIDE_VALUE_PREFIX = "value:"


_COMPARISON_ORDER = {None: 0, "sequential": 1, "yoy": 2}


def _wide_table(rows: list[TableRow], *, intent: Intent | None) -> DisplayTable | None:
    """A row per company and quarter (and change), a column per metric.

    "How is Apple doing?" and "their operating margin" read across a row, not
    down a list of company-metric pairs; over a window, each quarter is one row
    and each change one more. Provenance stays per value in the evidence list,
    so the wide table carries no filing columns.
    """
    metrics = list(dict.fromkeys(row.metric for row in rows if row.metric))
    if len(metrics) < 2 and (len(rows) < 2 or intent in (Intent.RANK, Intent.RANK_AND_LOOKUP)):
        return None
    cells: dict[tuple[str, date | None, str | None], dict[str, TableRow]] = {}
    for row in rows:
        place: tuple[str, date | None, str | None] = (
            row.cik or row.company_name,
            row.end_date,
            row.comparison,
        )
        if row.metric in cells.setdefault(place, {}):
            return None
        cells[place][row.metric] = row
    # Failed cells carry no date: fold them into their company's only row.
    for undated in [place for place in cells if place[1] is None and place[2] is None]:
        dated = [other for other in cells if other[0] == undated[0] and other != undated]
        if len(dated) == 1 and not set(cells[undated]) & set(cells[dated[0]]):
            cells[dated[0]].update(cells.pop(undated))
    entities = list(dict.fromkeys(slot[0] for slot in cells))
    ordered = sorted(
        cells,
        key=lambda slot: (
            entities.index(slot[0]),
            _COMPARISON_ORDER.get(slot[2], 3) > 0,
            -(slot[1].toordinal() if slot[1] else 0),
            _COMPARISON_ORDER.get(slot[2], 3),
        ),
    )
    ranked = intent in (Intent.RANK, Intent.RANK_AND_LOOKUP) and any(
        row.rank is not None for row in rows
    )
    changes = any(slot[2] is not None for slot in cells)
    keys = [
        *(["rank"] if ranked else []),
        "company_name",
        "ticker",
        *(["comparison"] if changes else []),
        *(f"{WIDE_VALUE_PREFIX}{metric}" for metric in metrics),
        "end_date",
    ]
    headers = tuple(
        _humanize_field(key[len(WIDE_VALUE_PREFIX) :])
        if key.startswith(WIDE_VALUE_PREFIX)
        else "Quarter ended"
        if key == "end_date"
        else format_field_name(key)
        for key in keys
    )
    rendered: list[tuple[str, ...]] = []
    numbers: list[tuple[int | float | None, ...]] = []
    for group in ordered:
        by_metric = cells[group]
        first = next(iter(by_metric.values()))
        identity = next((row for row in by_metric.values() if row.ticker), first)
        ends = [row.end_date for row in by_metric.values() if row.end_date is not None]
        text: list[str] = []
        values: list[int | float | None] = []
        for key in keys:
            if key.startswith(WIDE_VALUE_PREFIX):
                cell = by_metric.get(key[len(WIDE_VALUE_PREFIX) :])
                if cell is None:
                    text.append("")
                    values.append(None)
                elif cell.value is None:
                    # A narrow cell: the label alone ("Missing fact"), code in evidence.
                    text.append(_REASON_LABELS.get(cell.reason or "", "") or "")
                    values.append(None)
                else:
                    text.append(_format_cell(cell, "value"))
                    values.append(float(cell.value))
            elif key == "end_date":
                text.append(format_date(max(ends)) if ends else "")
                values.append(None)
            elif key == "rank":
                rank = identity.rank if identity.rank is not None else first.rank
                text.append(str(rank) if rank is not None else "")
                values.append(rank)
            elif key == "comparison":
                text.append(_format_cell(first, "comparison"))
                values.append(None)
            else:
                text.append(_format_cell(identity, key))
                values.append(None)
        rendered.append(tuple(text))
        numbers.append(tuple(values))
    if not any(value is not None for row in numbers for value in row):
        return None
    return DisplayTable(
        headers=headers, keys=tuple(keys), rows=tuple(rendered), numbers=tuple(numbers)
    )


def _display_table(rows: list[TableRow], *, intent: Intent | None = None) -> DisplayTable:
    wide = _wide_table(rows, intent=intent)
    if wide is not None:
        return wide
    allowed = (
        _RANK_TABLE_KEYS
        if intent in (Intent.RANK, Intent.RANK_AND_LOOKUP)
        else _TABLE_KEYS
    )
    keys = [key for key in allowed if any(not _cell_empty(getattr(row, key)) for row in rows)]
    metrics = {row.metric for row in rows if row.metric}
    single_metric = len(metrics) == 1
    value_header = _humanize_field(next(iter(metrics))) if single_metric else None
    if single_metric:
        keys = [key for key in keys if key != "metric"]
        if "value" not in keys:
            insert_at = 0
            for marker in ("ticker", "company_name", "rank"):
                if marker in keys:
                    insert_at = keys.index(marker) + 1
                    break
            keys.insert(insert_at, "value")
    headers = tuple(
        value_header if key == "value" and value_header else format_field_name(key)
        for key in keys
    )
    rendered = tuple(tuple(_format_cell(row, key) for key in keys) for row in rows)
    numbers = tuple(tuple(_numeric_cell(row, key) for key in keys) for row in rows)
    return DisplayTable(headers=headers, keys=tuple(keys), rows=rendered, numbers=numbers)


def _format_cell(row: TableRow, key: str) -> str:
    value = getattr(row, key)
    if key == "comparison":
        return _COMPARISON_LABELS.get(str(value), _LEVEL_LABEL) if value else _LEVEL_LABEL
    if _cell_empty(value):
        return ""
    if key == "value":
        if row.comparison is not None and row.metric in PERCENT_FORMULAS:
            # A change in a margin is in percentage points, not percent.
            points = (value * Decimal("100")).quantize(_TENTH, rounding=ROUND_HALF_UP)
            formatted = f"{'+' if points > 0 else ''}{points:.1f} pts"
        else:
            formatted = format_metric_value(row.metric, value)
            if row.comparison is not None and value > 0:
                formatted = f"+{formatted}"
        return formatted + (DERIVED_MARK if is_derived(row) else "")
    if key == "metric":
        return _humanize_field(str(value))
    if key in {"start_date", "end_date"}:
        return format_date(value)
    if key == "reason":
        return format_reason(value)
    if key == "rank":
        return str(value)
    return str(value)


def _format_banner(banner: str) -> str:
    if banner in _BANNER_COPY:
        return _BANNER_COPY[banner]
    if not banner.startswith(_SNAPSHOT_PREFIX):
        return banner
    parsed = try_parse_datetime(banner[len(_SNAPSHOT_PREFIX) :])
    if parsed is None:
        return banner
    return f"{_SNAPSHOT_PREFIX}{format_datetime_utc(parsed)}"


def _trace_identity(args: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("company", "metric", "industry", "query", "topic"):
        value = args.get(key)
        if value is not None and value != "":
            parts.append(_humanize_field(str(value)) if key == "metric" else str(value))
    issuers = args.get("issuers")
    if isinstance(issuers, list) and issuers:
        parts.append(", ".join(str(item) for item in issuers))
    return " · ".join(parts)


_SOURCE_LABELS = {
    "sec_xbrl": "SEC EDGAR",
}


def _truncate_url(url: str, max_len: int = 48) -> str:
    if len(url) <= max_len:
        return url
    parsed = urlparse(url)
    name = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if parsed.netloc and name:
        compact = f"{parsed.netloc}/…/{name}"
        if len(compact) < len(url):
            return compact
    keep = max(max_len - 1, 1)
    head = max(keep // 2, 1)
    tail = max(keep - head, 1)
    return f"{url[:head]}…{url[-tail:]}"


def _append_trace_field(
    fields: list[tuple[str, str]], key: str, value: Any
) -> None:
    label = _humanize_field(str(key))
    if key == "components" and isinstance(value, list):
        _append_component_fields(fields, value)
        return
    if key == "derivation" and isinstance(value, dict):
        _append_derivation_fields(fields, value)
        return
    if key == "hits" and isinstance(value, list):
        fields.append((label, _format_hit_traces(value)))
        return
    if key == "metric" and isinstance(value, str):
        fields.append((label, _humanize_field(value)))
        return
    if key == "source_url" and value:
        url = str(value)
        fields.append((label, f"[{_truncate_url(url)}]({url})"))
        return
    if key == "source" and value:
        raw = str(value)
        fields.append((label, _SOURCE_LABELS.get(raw, raw)))
        return
    fields.append((label, _format_trace_value(value)))


def _trace_fields(payload: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    fields: list[tuple[str, str]] = []
    for key, value in payload.items():
        _append_trace_field(fields, str(key), value)
    return tuple(fields)


def _names_by_cik(rows: list[TableRow]) -> dict[str, str]:
    return {row.cik: row.company_name for row in rows if row.cik and row.company_name}


def _display_trace(trace: Any, *, names: dict[str, str] | None = None) -> DisplayTrace:
    args = dict(trace.args)
    company = args.get("company")
    if names and isinstance(company, str) and company in names:
        # Ranked lookups run by CIK; the header reads better with the name.
        args["company"] = names[company]
    issuers = args.get("issuers")
    if names and isinstance(issuers, list):
        args["issuers"] = [names.get(str(item), item) for item in issuers]
    identity = _trace_identity(args)
    period = _trace_period(trace)
    what = identity or "this request"
    template = _TOOL_HEADERS.get(str(trace.tool))
    if template:
        header = template.format(what=what)
    elif identity:
        header = f"{trace.tool} · {identity}"
    else:
        header = str(trace.tool)
    if period:
        header = f"{header} ({period})"
    return DisplayTrace(
        header=header,
        inputs=_trace_fields(trace.args),
        outputs=_trace_fields(trace.provenance),
    )


def _format_component_amount(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, Decimal):
        return format_usd(value)
    try:
        return format_usd(Decimal(str(value)))
    except InvalidOperation:
        return str(value)


_COMPONENT_FIELD_ORDER = (
    "concept",
    "taxonomy",
    "accession_number",
    "form",
    "start_date",
    "end_date",
    "source",
    "source_url",
)


def _append_derivation_fields(fields: list[tuple[str, str]], derivation: dict[str, Any]) -> None:
    fields.append(("Derived", str(derivation.get("label") or "Derived quarter")))
    parts = derivation.get("parts")
    if not isinstance(parts, list):
        return
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        period = _period_label(
            _as_iso_date(part.get("start_date")), _as_iso_date(part.get("end_date"))
        )
        label = f"{'Minus ' if index else ''}{part.get('form') or 'Filing'} {period}".strip()
        nested = part.get("derivation")
        if isinstance(nested, dict):
            # A derived part (a fiscal Q4 inside a gross profit) lists its own filings.
            fields.append((f"{label} †", _format_component_amount(part.get("value"))))
            _append_derivation_fields(fields, nested)
            continue
        fields.append((label, _format_component_amount(part.get("value"))))
        url = part.get("source_url")
        if url:
            _append_trace_field(fields, "source_url", url)


def _append_component_fields(fields: list[tuple[str, str]], components: list[Any]) -> None:
    for index, item in enumerate(components):
        if not isinstance(item, dict):
            fields.append(("", _format_trace_value(item)))
            continue
        if index:
            fields.append(("", ""))
        metric = _humanize_field(str(item.get("metric") or "Component"))
        fields.append((metric, _format_component_amount(item.get("value"))))
        for key in _COMPONENT_FIELD_ORDER:
            raw = item.get(key)
            if raw:
                _append_trace_field(fields, key, raw)


_SNIPPET_DISPLAY_LIMIT = 280
_HIT_KNOWN_KEYS = frozenset({"title", "url", "snippet", "score", "published"})
_HIT_HIDDEN_KEYS = frozenset({"raw_content", "content", "favicon", "images"})
_MARKDOWN_ESCAPE = str.maketrans(
    {
        "\\": "\\\\",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "#": "\\#",
        "!": "\\!",
        "|": "\\|",
        "$": "\\$",
    }
)


def _escape_markdown(text: str) -> str:
    return text.translate(_MARKDOWN_ESCAPE)


def _format_hit_snippet(value: Any) -> str:
    text = " ".join(str(value).split())
    if len(text) > _SNIPPET_DISPLAY_LIMIT:
        text = text[: _SNIPPET_DISPLAY_LIMIT - 1].rstrip() + "…"
    return _escape_markdown(text)


def _format_hit_score(value: Any) -> str:
    if isinstance(value, bool):
        return _escape_markdown(str(value))
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    try:
        return f"{float(str(value).strip()):.2f}"
    except ValueError:
        return _escape_markdown(str(value))


def _format_hit_traces(hits: list[Any]) -> str:
    blocks: list[str] = []
    for index, item in enumerate(hits, start=1):
        if not isinstance(item, dict):
            blocks.append(f"- **[{index}]** {_escape_markdown(_format_trace_value(item))}")
            continue
        title = _escape_markdown(str(item.get("title") or f"Hit {index}"))
        url = str(item.get("url") or "").strip()
        heading = f"- **[{index}]** [{title}]({url})" if url else f"- **[{index}]** {title}"
        lines = [heading]
        score = item.get("score")
        if score is not None and score != "":
            lines.append(f"  - Score: `{_format_hit_score(score)}`")
        published = item.get("published")
        if published:
            lines.append(f"  - Published: {_format_trace_value(published)}")
        for key, value in item.items():
            if key in _HIT_KNOWN_KEYS or key in _HIT_HIDDEN_KEYS:
                continue
            if value is None or value == "" or isinstance(value, (dict, list)):
                continue
            lines.append(
                f"  - {_humanize_field(str(key))}: {_escape_markdown(_format_trace_value(value))}"
            )
        snippet = item.get("snippet")
        if snippet:
            lines.append(f"  - Snippet: {_format_hit_snippet(snippet)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _format_trace_value(value: Any) -> str:
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, date):
        return format_date(value)
    if isinstance(value, (int, bool)):
        return str(value)
    if isinstance(value, Decimal):
        return format_usd(value)
    if isinstance(value, str):
        parsed = try_parse_datetime(value)
        if parsed is not None and ("T" in value or " " in value.strip()):
            return format_datetime_utc(parsed)
        try:
            as_date = date.fromisoformat(value)
        except ValueError:
            return value
        return format_date(as_date)
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            label = _humanize_field(str(key))
            formatted = _format_trace_value(item)
            if isinstance(item, (dict, list)):
                lines.append(f"{label}:")
                lines.extend(f"  {line}" for line in formatted.splitlines())
            else:
                lines.append(f"{label}: {formatted}")
        return "\n".join(lines)
    if isinstance(value, list):
        if value and all(not isinstance(item, (dict, list)) for item in value):
            return ", ".join(_format_trace_value(item) for item in value)
        lines = []
        for item in value:
            item_lines = _format_trace_value(item).splitlines()
            if not item_lines:
                lines.append("- ")
                continue
            lines.append(f"- {item_lines[0]}")
            lines.extend(f"  {line}" for line in item_lines[1:])
        return "\n".join(lines)
    return str(value)


def _display_citation(index: int, hit: Any) -> DisplayCitation:
    published = hit.published
    if published:
        published = _format_trace_value(published)
    return DisplayCitation(index=index, title=hit.title, url=hit.url, published=published)


def _join_words(words: list[str]) -> str:
    """Join words in prose: "A", "A and B", "A, B and C"."""
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} and {words[-1]}"
