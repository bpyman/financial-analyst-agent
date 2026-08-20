from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from financial_analyst_agent.turn import (
    ALLOWED_METRICS,
    REPORTED_METRICS,
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
    "rank",
    "company_name",
    "ticker",
    "cik",
    "metric",
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


def metric_legend() -> tuple[str, ...]:
    return tuple(_humanize_field(metric) for metric in ALLOWED_METRICS)


def metric_groups() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        ("Reported", tuple(_humanize_field(metric) for metric in REPORTED_METRICS)),
        ("Margins", tuple(_humanize_field(metric) for metric in FORMULA_METRICS)),
    )


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
        citations=tuple(
            _display_citation(index, hit) for index, hit in enumerate(result.citations, start=1)
        ),
        fact_card=fact_card,
        table=table,
        essay=result.essay,
        message=result.message if result.renderer is not RendererKind.CLARIFY else None,
        candidates=tuple(_humanize_field(name) for name in result.candidates),
    )


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
    return QuarterlyFactCard(
        company_name=row.company_name,
        ticker=row.ticker,
        metric_header=_humanize_field(row.metric),
        amount=format_metric_value(row.metric, row.value),
        period_label=(
            "Latest standalone quarter · "
            f"{format_date(row.start_date)} – {format_date(row.end_date)}"
        ),
        form=form,
        accession_number=accession_number,
        concept=concept,
        source_url=source_url,
    )


def _cell_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _display_table(rows: list[TableRow]) -> DisplayTable:
    keys = [key for key in _TABLE_KEYS if any(not _cell_empty(getattr(row, key)) for row in rows)]
    headers = tuple(format_field_name(key) for key in keys)
    rendered = tuple(tuple(_format_cell(row, key) for key in keys) for row in rows)
    return DisplayTable(headers=headers, keys=tuple(keys), rows=rendered)


def _format_cell(row: TableRow, key: str) -> str:
    value = getattr(row, key)
    if _cell_empty(value):
        return ""
    if key == "value":
        return format_metric_value(row.metric, value)
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
_FILING_FIELD_ORDER = (
    "form",
    "accession_number",
    "taxonomy",
    "concept",
    "start_date",
    "end_date",
    "source",
    "source_url",
)
_FILING_TRACE_KEYS = frozenset(_FILING_FIELD_ORDER)


def _is_filing_provenance(payload: dict[str, Any]) -> bool:
    return (
        "accession_number" in payload
        and "components" not in payload
        and "hits" not in payload
    )


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
        raw = value.value if hasattr(value, "value") else str(value)
        fields.append((label, _SOURCE_LABELS.get(raw, raw)))
        return
    fields.append((label, _format_trace_value(value)))


def _trace_fields(payload: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    fields: list[tuple[str, str]] = []
    if _is_filing_provenance(payload):
        ordered = [key for key in _FILING_FIELD_ORDER if key in payload]
        ordered.extend(key for key in payload if key not in _FILING_TRACE_KEYS)
        for key in ordered:
            _append_trace_field(fields, str(key), payload[key])
        return tuple(fields)
    for key, value in payload.items():
        _append_trace_field(fields, str(key), value)
    return tuple(fields)


def _display_trace(trace: Any) -> DisplayTrace:
    identity = _trace_identity(trace.args)
    header = f"{trace.tool} · {identity}" if identity else trace.tool
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
