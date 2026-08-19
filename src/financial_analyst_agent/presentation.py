from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from financial_analyst_agent.turn import (
    ALLOWED_METRICS,
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

FORMULA_METRICS = ("gross_margin", "operating_margin", "net_margin")

_REASON_LABELS = {
    "missing_fact": "Missing fact",
    "period_mismatch": "Period mismatch",
    "ambiguous_concept": "Ambiguous concept",
    "zero_denominator": "Zero denominator",
}
_FIELD_LABELS = {
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
    "gross_margin": "Gross margin",
    "operating_margin": "Operating margin",
    "net_margin": "Net margin",
}


def format_usd(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    amount = abs(value)
    if amount == 0:
        return "$0"
    if amount >= _TRILLION:
        scaled = (amount / _TRILLION).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return f"{sign}${scaled:.2f} T"
    if amount >= _BILLION:
        scaled = (amount / _BILLION).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return f"{sign}${scaled:.2f} B"
    if amount >= _MILLION:
        scaled = (amount / _MILLION).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return f"{sign}${scaled:.2f} M"
    grouped = f"{int(amount):,}"
    return f"{sign}${grouped}"


def format_percent(ratio: Decimal) -> str:
    percent = (ratio * Decimal("100")).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f"{percent:.1f}%"


def format_date(value: date) -> str:
    return f"{_MONTHS[value.month - 1]} {value.day}, {value.year}"


def format_datetime_utc(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    utc = aware.astimezone(UTC)
    hour12 = utc.hour % 12 or 12
    suffix = "AM" if utc.hour < 12 else "PM"
    return f"{format_date(utc.date())}, {hour12}:{utc.minute:02d} {suffix} UTC"


def format_field_name(key: str) -> str:
    label = _FIELD_LABELS.get(key)
    if label is None:
        label = " ".join(part.capitalize() for part in key.split("_"))
    return f"{key} ({label})"


def format_reason(reason: str) -> str:
    label = _REASON_LABELS.get(reason)
    if label is None:
        label = " ".join(part.capitalize() for part in reason.split("_"))
    return f"{reason} ({label})"


def format_metric_value(metric: str, value: Decimal | None) -> str:
    if value is None:
        return ""
    if metric in FORMULA_METRICS:
        return format_percent(value)
    return format_usd(value)


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
    "company_name",
    "ticker",
    "cik",
    "metric",
    "rank",
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
_SNAPSHOT_PREFIX = "Universe snapshot as of "


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


@dataclass(frozen=True)
class DisplayTrace:
    header: str
    fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DisplayCitation:
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


def metric_legend() -> tuple[str, ...]:
    return tuple(format_field_name(metric) for metric in ALLOWED_METRICS)


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
    elif result.renderer is RendererKind.TABLE:
        table = _display_table(result.table_rows)
    return Presentation(
        intent=result.intent.value,
        banners=tuple(_format_banner(banner) for banner in result.banners),
        traces=tuple(_display_trace(trace) for trace in result.tool_traces),
        citations=tuple(_display_citation(hit) for hit in result.citations),
        fact_card=fact_card,
        table=table,
        essay=result.essay,
        message=result.message,
    )


def _fact_card(row: TableRow) -> QuarterlyFactCard:
    assert row.start_date is not None
    assert row.end_date is not None
    return QuarterlyFactCard(
        company_name=row.company_name,
        ticker=row.ticker,
        metric_header=format_field_name(row.metric),
        amount=format_metric_value(row.metric, row.value),
        period_label=(
            "Latest standalone quarter · "
            f"{format_date(row.start_date)} – {format_date(row.end_date)}"
        ),
        form=row.form or "",
        accession_number=row.accession_number or "",
        concept=row.concept or "",
        source_url=row.source_url or "",
    )


def _cell_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _display_table(rows: list[TableRow]) -> DisplayTable:
    keys = [
        key
        for key in _TABLE_KEYS
        if any(not _cell_empty(getattr(row, key)) for row in rows)
    ]
    headers = tuple(format_field_name(key) for key in keys)
    rendered = tuple(tuple(_format_cell(row, key) for key in keys) for row in rows)
    return DisplayTable(headers=headers, keys=tuple(keys), rows=rendered)


def _format_cell(row: TableRow, key: str) -> str:
    value = getattr(row, key)
    if _cell_empty(value):
        return ""
    if key == "value":
        return format_metric_value(row.metric, value)
    if key in {"start_date", "end_date"}:
        return format_date(value)
    if key == "reason":
        return format_reason(value)
    if key == "rank":
        return str(value)
    return str(value)


def _format_banner(banner: str) -> str:
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
            parts.append(str(value))
    issuers = args.get("issuers")
    if isinstance(issuers, list) and issuers:
        parts.append(", ".join(str(item) for item in issuers))
    return " · ".join(parts)


def _display_trace(trace: Any) -> DisplayTrace:
    identity = _trace_identity(trace.args)
    header = f"{trace.tool} · {identity}" if identity else trace.tool
    fields: list[tuple[str, str]] = []
    for key, value in {**trace.args, **trace.provenance}.items():
        fields.append((format_field_name(str(key)), _format_trace_value(value)))
    return DisplayTrace(header=header, fields=tuple(fields))


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
        return "; ".join(
            f"{format_field_name(str(key))}: {_format_trace_value(item)}"
            for key, item in value.items()
        )
    if isinstance(value, list):
        return ", ".join(_format_trace_value(item) for item in value)
    return str(value)


def _display_citation(hit: Any) -> DisplayCitation:
    published = hit.published
    if published:
        published = _format_trace_value(published)
    return DisplayCitation(title=hit.title, url=hit.url, published=published)
