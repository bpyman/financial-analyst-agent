# Polished Audience Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Streamlit audience window so a turn’s quarterly fact, tables, essays, and refuses read like a dense financial terminal without changing `run_turn`.

**Architecture:** Keep `run_turn(query, runtime) -> TurnResult` as the only feature seam. Add a pure `present_turn(result) -> Presentation` mapping that formats compact USD, dates, empty-column tables, and domain-then-humanized labels. Streamlit plus streamlit-shadcn-ui only paint that mapping. Live and fixture share the same renderer; the kill-switch still only swaps adapters.

**Tech Stack:** Python 3.12, Streamlit ≥1.61, streamlit-shadcn-ui ≥1.0, pytest, mypy strict.

**Spec:** `.scratch/audience-window/issues/01-polished-audience-window.md`

## Global Constraints

- Presentation only: do not change `run_turn`, planner intents, MCP tools, quarterly-fact lookup, snapshot membership, or numeral lock.
- Third-party kit is streamlit-shadcn-ui for the quarterly-fact hero and status chrome (`metric_card`, `badge`). Native Streamlit remains for dataframe, sidebar toggle, form, expander, banners, and essay markdown.
- Dark Streamlit theme: inherit dark base; near-black canvas `#0b0d10`; widget fill `#181a1f`; primary blue `#3b82f6`; sharp radius (`none`); widget borders on; Inter; toolbar minimal so Deploy is gone. Green `#22c55e` / red `#ef4444` for Live vs Fixture/refuse. Do not vendor a Bloomberg stylesheet.
- One shell for every renderer kind. Lookup hero is a starting layout, not a pixel spec.
- Compact USD: suffix T/B/M at 1e12 / 1e9 / 1e6; two decimal places; round half up; `$` prefix; space before the letter; below 1e6 grouped dollars and no suffix. Apply to every dollar figure including market cap.
- Margins (`gross_margin`, `operating_margin`, `net_margin`) display as a percentage with one decimal place, not compact USD.
- Date-only: `MMM D, YYYY` (English month, no leading zero on day). Datetimes: same date plus time without seconds, UTC, with a `UTC` label.
- Omit a table column when every cell on this turn is empty or null. Do not hard-hide `rank` on lookup by special case if the empty-column rule already drops it. Omit the nested `components` column from the table (provenance stays on the tool trace).
- Headers and reasons: domain identifier first, humanized label in parentheses. Reasons: `missing_fact (Missing fact)`, `period_mismatch (Period mismatch)`, `ambiguous_concept (Ambiguous concept)`, `zero_denominator (Zero denominator)`.
- Input label is “Ask a question”. Gold Google latest-quarter net income query stays the default value. No prompt chips.
- Ask lives in a form (Enter submits). Spinner during `run_turn`. Prevent a second submit until that call returns. Cache the turn result; reruns without a new submit must not call `run_turn` again.
- Sidebar starts collapsed. Kill-switch toggle stays in the sidebar. Header pill shows Live or Fixture. Fixture still shows the existing announce-out-loud banner.
- Tool expanders start collapsed. Header is tool name plus a short identity from args. Body is labeled key-value, not `st.json`.
- Period copy on a quarterly fact: “Latest standalone quarter” plus formatted start and end. No period picker. Do not echo a user-typed historical quarter.
- Tests assert display records and shell behavior, not shadcn internals or CSS. Gold tests stay on `run_turn` and must remain green unchanged.
- Commits: one-line why-focused messages (repo style). On Windows PowerShell use `git commit -m "message"` (no bash heredoc).

## File map

- Create: `src/financial_analyst_agent/presentation.py` — pure formatters + `present_turn`. No Streamlit imports.
- Create: `tests/test_presentation.py` — Seam 2.
- Create: `.streamlit/config.toml` — dark theme + minimal toolbar.
- Modify: `pyproject.toml` — add `streamlit-shadcn-ui>=1.0.0`.
- Modify: `src/financial_analyst_agent/app.py` — shell + paint `Presentation`.
- Modify: `tests/test_app.py` — Seam 1: form submit, collapsed sidebar, cached `run_turn`.

Do not modify `turn.py`.

---

### Task 1: Scalar formatters

**Files:**
- Create: `src/financial_analyst_agent/presentation.py`
- Test: `tests/test_presentation.py`

**Interfaces:**
- Consumes: `decimal.Decimal`, `datetime.date`, `datetime.datetime`
- Produces:
  - `format_usd(value: Decimal) -> str`
  - `format_percent(ratio: Decimal) -> str`
  - `format_date(value: date) -> str`
  - `format_datetime_utc(value: datetime) -> str`
  - `format_field_name(key: str) -> str`
  - `format_reason(reason: str) -> str`
  - `format_metric_value(metric: str, value: Decimal | None) -> str`
  - `try_parse_datetime(raw: str) -> datetime | None`

- [ ] **Step 1: Write the failing compact-USD tests**

```python
from datetime import date, datetime, timezone
from decimal import Decimal

from financial_analyst_agent.presentation import format_usd


def test_format_usd_billions_half_up() -> None:
    assert format_usd(Decimal("112193000000")) == "$112.19 B"


def test_format_usd_alphabet_net_income() -> None:
    assert format_usd(Decimal("62578000000")) == "$62.58 B"


def test_format_usd_exact_hundreds_of_billions() -> None:
    assert format_usd(Decimal("800000000000")) == "$800.00 B"


def test_format_usd_under_one_million_is_grouped() -> None:
    assert format_usd(Decimal("500000")) == "$500,000"


def test_format_usd_one_million_uses_suffix() -> None:
    assert format_usd(Decimal("1000000")) == "$1.00 M"


def test_format_usd_one_trillion() -> None:
    assert format_usd(Decimal("1000000000000")) == "$1.00 T"


def test_format_usd_zero() -> None:
    assert format_usd(Decimal("0")) == "$0"


def test_format_usd_negative() -> None:
    assert format_usd(Decimal("-1500000000")) == "-$1.50 B"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_presentation.py::test_format_usd_billions_half_up -v`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `financial_analyst_agent.presentation`.

- [ ] **Step 3: Write minimal `format_usd`**

In `src/financial_analyst_agent/presentation.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
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
        return f"{sign}${scaled} T"
    if amount >= _BILLION:
        scaled = (amount / _BILLION).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return f"{sign}${scaled} B"
    if amount >= _MILLION:
        scaled = (amount / _MILLION).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return f"{sign}${scaled} M"
    grouped = f"{int(amount):,}"
    return f"{sign}${grouped}"
```

Quantize output must show two decimal places (`Decimal("800.00")` stringifies as `800.00` in Python 3.12). If a test fails because `800.0` is printed, format with `f"{sign}${scaled:.2f} T"` after converting scaled to a string that always has two places: `f"{sign}${format(scaled, 'f')} T"` is not enough for integers; use `f"{sign}${scaled.quantize(_CENTS):.2f} B"` — `:.2f` on Decimal is fine if we accept a tiny float conversion only in the display layer. Prefer:

```python
text = f"{scaled:.2f}"
return f"{sign}${text} B"
```

Do not use `float(value)` for the scale decision; compare Decimals.

- [ ] **Step 4: Run USD tests to verify they pass**

Run: `uv run pytest tests/test_presentation.py -k format_usd -v`

Expected: PASS (8 tests).

- [ ] **Step 5: Write failing date, percent, and label tests**

Append to `tests/test_presentation.py`:

```python
from financial_analyst_agent.presentation import (
    format_date,
    format_datetime_utc,
    format_field_name,
    format_metric_value,
    format_percent,
    format_reason,
    try_parse_datetime,
)


def test_format_date_has_no_leading_zero() -> None:
    assert format_date(date(2026, 1, 1)) == "Jan 1, 2026"
    assert format_date(date(2020, 6, 30)) == "Jun 30, 2020"


def test_format_datetime_utc_drops_seconds() -> None:
    stamp = datetime(2026, 8, 17, 16, 0, 0, tzinfo=timezone.utc)
    assert format_datetime_utc(stamp) == "Aug 17, 2026, 4:00 PM UTC"


def test_format_datetime_utc_converts_offset_and_drops_microseconds() -> None:
    stamp = datetime.fromisoformat("2026-08-18T09:10:30.074615+00:00")
    assert format_datetime_utc(stamp) == "Aug 18, 2026, 9:10 AM UTC"


def test_format_percent_one_decimal_half_up() -> None:
    ratio = Decimal("38398000000") / Decimal("82886000000")
    assert format_percent(ratio) == "46.3%"


def test_format_field_name_domain_first() -> None:
    assert format_field_name("company_name") == "company_name (Company)"
    assert format_field_name("cik") == "cik (CIK)"
    assert format_field_name("net_income") == "net_income (Net income)"


def test_format_reason_domain_first() -> None:
    assert format_reason("missing_fact") == "missing_fact (Missing fact)"
    assert format_reason("period_mismatch") == "period_mismatch (Period mismatch)"
    assert format_reason("ambiguous_concept") == "ambiguous_concept (Ambiguous concept)"
    assert format_reason("zero_denominator") == "zero_denominator (Zero denominator)"


def test_format_metric_value_blank_when_missing() -> None:
    assert format_metric_value("net_income", None) == ""


def test_format_metric_value_margin_is_percent() -> None:
    ratio = Decimal("39696000000") / Decimal("109896000000")
    assert format_metric_value("operating_margin", ratio) == "36.1%"


def test_format_metric_value_reported_is_usd() -> None:
    assert format_metric_value("net_income", Decimal("62578000000")) == "$62.58 B"


def test_format_metric_value_market_cap_is_usd() -> None:
    assert format_metric_value("market_cap", Decimal("800000000000")) == "$800.00 B"


def test_try_parse_datetime_iso() -> None:
    parsed = try_parse_datetime("2026-08-17T16:00:00+00:00")
    assert parsed is not None
    assert format_datetime_utc(parsed) == "Aug 17, 2026, 4:00 PM UTC"


def test_try_parse_datetime_unparseable_is_none() -> None:
    assert try_parse_datetime("yesterday morning") is None
```

- [ ] **Step 6: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_presentation.py::test_format_date_has_no_leading_zero -v`

Expected: FAIL with `ImportError` for the new names.

- [ ] **Step 7: Implement the remaining scalars**

Append to `presentation.py`:

```python
def format_percent(ratio: Decimal) -> str:
    percent = (ratio * Decimal("100")).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f"{percent:.1f}%"


def format_date(value: date) -> str:
    return f"{_MONTHS[value.month - 1]} {value.day}, {value.year}"


def format_datetime_utc(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    utc = aware.astimezone(timezone.utc)
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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
```

- [ ] **Step 8: Run all scalar tests**

Run: `uv run pytest tests/test_presentation.py -v`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/financial_analyst_agent/presentation.py tests/test_presentation.py
git commit -m "Format compact USD, dates, and domain-first labels for the audience window."
```

---

### Task 2: `present_turn` display records

**Files:**
- Modify: `src/financial_analyst_agent/presentation.py`
- Modify: `tests/test_presentation.py`

**Interfaces:**
- Consumes: `TurnResult`, `TableRow`, `ToolTrace`, `NewsHit`, `Intent`, `RendererKind` from `financial_analyst_agent.turn`; scalars from Task 1
- Produces:
  - `@dataclass(frozen=True) class QuarterlyFactCard` with `company_name: str`, `ticker: str`, `metric_header: str`, `amount: str`, `period_label: str`, `form: str`, `accession_number: str`, `concept: str`, `source_url: str`
  - `@dataclass(frozen=True) class DisplayTable` with `headers: tuple[str, ...]`, `keys: tuple[str, ...]`, `rows: tuple[tuple[str, ...], ...]`
  - `@dataclass(frozen=True) class DisplayTrace` with `header: str`, `fields: tuple[tuple[str, str], ...]`
  - `@dataclass(frozen=True) class DisplayCitation` with `title: str`, `url: str`, `published: str | None`
  - `@dataclass(frozen=True) class Presentation` with `intent: str`, `banners: tuple[str, ...]`, `traces: tuple[DisplayTrace, ...]`, `citations: tuple[DisplayCitation, ...]`, `fact_card: QuarterlyFactCard | None`, `table: DisplayTable | None`, `essay: str | None`, `message: str | None`
  - `present_turn(result: TurnResult) -> Presentation`
  - `metric_legend() -> tuple[str, ...]`

- [ ] **Step 1: Write the failing lookup-card and empty-column tests**

Append to `tests/test_presentation.py`:

```python
from financial_analyst_agent.presentation import present_turn
from financial_analyst_agent.turn import (
    Intent,
    RendererKind,
    TableRow,
    ToolTrace,
    TurnResult,
)


def _lookup_result() -> TurnResult:
    return TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args={"company": "Google", "metric": "net_income"},
                provenance={
                    "accession_number": "0001652044-26-000048",
                    "concept": "NetIncomeLoss",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm",
                    "start_date": "2026-01-01",
                    "end_date": "2026-03-31",
                },
            )
        ],
        table_rows=[
            TableRow(
                company_name="Alphabet Inc.",
                ticker="GOOG",
                cik="0001652044",
                metric="net_income",
                value=Decimal("62578000000"),
                currency="USD",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                form="10-Q",
                accession_number="0001652044-26-000048",
                taxonomy="us-gaap",
                concept="NetIncomeLoss",
                source_url="https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm",
            )
        ],
    )


def test_present_lookup_uses_fact_card_not_table() -> None:
    presented = present_turn(_lookup_result())
    assert presented.intent == "lookup"
    assert presented.table is None
    card = presented.fact_card
    assert card is not None
    assert card.company_name == "Alphabet Inc."
    assert card.ticker == "GOOG"
    assert card.metric_header == "net_income (Net income)"
    assert card.amount == "$62.58 B"
    assert card.period_label == "Latest standalone quarter · Jan 1, 2026 – Mar 31, 2026"
    assert card.form == "10-Q"
    assert card.accession_number == "0001652044-26-000048"
    assert card.concept == "NetIncomeLoss"
    assert card.source_url.endswith("goog-20260331.htm")


def test_present_lookup_omits_empty_rank_if_table_used() -> None:
    result = _lookup_result()
    result = result.model_copy(update={"intent": Intent.COMPARE})
    presented = present_turn(result)
    assert presented.table is not None
    assert "rank" not in presented.table.keys
    assert "company_name (Company)" in presented.table.headers
```

The second test uses a lookup-shaped row under `compare` only to lock the empty-column rule without a lookup table. Prefer instead a dedicated rank-like row missing `form` etc.:

Replace `test_present_lookup_omits_empty_rank_if_table_used` with:

```python
def test_present_rank_omits_empty_fact_columns_and_formats_market_cap() -> None:
    result = TurnResult(
        intent=Intent.RANK,
        renderer=RendererKind.TABLE,
        banners=["Universe snapshot as of 2026-08-17T16:00:00+00:00"],
        tool_traces=[
            ToolTrace(
                tool="rank_companies",
                args={"industry": "healthcare", "limit": 10},
                provenance={"snapshot_as_of": "2026-08-17T16:00:00+00:00"},
            )
        ],
        table_rows=[
            TableRow(
                company_name="Eli Lilly and Company",
                ticker="LLY",
                cik="0000059478",
                metric="market_cap",
                rank=1,
                value=Decimal("800000000000"),
                currency="USD",
            )
        ],
    )
    presented = present_turn(result)
    assert presented.fact_card is None
    table = presented.table
    assert table is not None
    assert "rank" in table.keys
    assert "form" not in table.keys
    assert "reason" not in table.keys
    assert table.headers[0] == "company_name (Company)"
    rank_index = table.keys.index("rank")
    value_index = table.keys.index("value")
    assert table.rows[0][rank_index] == "1"
    assert table.rows[0][value_index] == "$800.00 B"
    assert presented.banners == ("Universe snapshot as of Aug 17, 2026, 4:00 PM UTC",)
```

- [ ] **Step 2: Run the lookup test to verify it fails**

Run: `uv run pytest tests/test_presentation.py::test_present_lookup_uses_fact_card_not_table -v`

Expected: FAIL with `ImportError` for `present_turn`.

- [ ] **Step 3: Implement `present_turn` and supporting types**

Append to `presentation.py` (keep the scalar functions already there):

```python
from dataclasses import dataclass
from typing import Any

from financial_analyst_agent.turn import (
    ALLOWED_METRICS,
    Intent,
    RendererKind,
    TableRow,
    TurnResult,
)

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
        parsed = try_parse_datetime(published)
        published = format_datetime_utc(parsed) if parsed is not None else published
    return DisplayCitation(title=hit.title, url=hit.url, published=published)
```

Avoid circular imports: `turn.py` must not import `presentation.py`. Only presentation imports turn.

If `format_usd` on a non-money trace scalar (for example `limit: 10` as int) is wrong, `_format_trace_value` should `str()` ints/bools before Decimal. `limit` is int — `str(value)` at the end covers it. Do not send ints through `format_usd`.

Trace ISO date-only strings (`2026-01-01`) must use `format_date`, not datetime. The `"T" in value` guard above does that.

- [ ] **Step 4: Run lookup and rank presentation tests**

Run: `uv run pytest tests/test_presentation.py -k "present_lookup or present_rank" -v`

Expected: PASS.

- [ ] **Step 5: Write failing compare, partial-reason, news, refuse, and legend tests**

```python
from financial_analyst_agent.presentation import metric_legend
from financial_analyst_agent.turn import NewsHit


def test_present_compare_formats_percent_and_keeps_reason() -> None:
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={"issuers": ["Microsoft", "Google"], "metric": "operating_margin"},
            )
        ],
        table_rows=[
            TableRow(
                company_name="Microsoft Corporation",
                ticker="MSFT",
                cik="0000789019",
                metric="operating_margin",
                reason="missing_fact",
            ),
            TableRow(
                company_name="Alphabet Inc.",
                ticker="GOOG",
                cik="0001652044",
                metric="operating_margin",
                value=Decimal("39696000000") / Decimal("109896000000"),
                currency="USD",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            ),
        ],
    )
    presented = present_turn(result)
    table = presented.table
    assert table is not None
    assert "reason" in table.keys
    reason_index = table.keys.index("reason")
    value_index = table.keys.index("value")
    assert table.rows[0][reason_index] == "missing_fact (Missing fact)"
    assert table.rows[0][value_index] == ""
    assert table.rows[1][value_index] == "36.1%"
    assert presented.traces[0].header.startswith("compare_metrics ·")


def test_present_news_keeps_unparseable_published() -> None:
    result = TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="Supply chain remains tight.",
        citations=[
            NewsHit(title="Hit", url="https://example.com/n", published="yesterday morning")
        ],
        tool_traces=[ToolTrace(tool="search_news", args={"query": "NVIDIA"})],
    )
    presented = present_turn(result)
    assert presented.citations[0].published == "yesterday morning"
    assert presented.essay == "Supply chain remains tight."
    assert presented.table is None
    assert presented.fact_card is None


def test_present_refuse_keeps_message() -> None:
    result = TurnResult(
        intent=Intent.RANK,
        renderer=RendererKind.REFUSE,
        message="Unknown industry 'AI'. Allowed: finance, healthcare, technology",
        tool_traces=[],
    )
    presented = present_turn(result)
    assert presented.message is not None
    assert "AI" in presented.message
    assert presented.table is None


def test_metric_legend_lists_closed_catalog() -> None:
    legend = metric_legend()
    assert legend[0] == "revenue (Revenue)"
    assert "operating_margin (Operating margin)" in legend
    assert len(legend) == 9
```

- [ ] **Step 6: Run the new tests (they should pass if Step 3 already covers them; if not, fix `present_turn`)**

Run: `uv run pytest tests/test_presentation.py -v`

Expected: PASS. If compare `value` index fails because empty-column omitted `value` on a mixed table: **do not omit `value` when any row has a value; the empty-column rule is per-column across all rows**, so `value` stays because Alphabet has a value, and Microsoft’s cell is `""`. That is already `_display_table`.

- [ ] **Step 7: Commit**

```bash
git add src/financial_analyst_agent/presentation.py tests/test_presentation.py
git commit -m "Map turn results to formatted display records so Streamlit does not format numbers."
```

---

### Task 3: Dark theme, shadcn, and the Streamlit shell

**Files:**
- Create: `.streamlit/config.toml`
- Modify: `pyproject.toml` (add `streamlit-shadcn-ui>=1.0.0` to `dependencies`)
- Modify: `src/financial_analyst_agent/app.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: `present_turn`, `Presentation`, `QuarterlyFactCard`, `DisplayTable`, `metric_legend` from Task 2; `KILL_SWITCH_BANNER` copy unchanged; `run_turn`, `runtime_for_kill_switch`
- Produces: Streamlit `main()` that submits via `st.form` / `st.form_submit_button`, collapsed sidebar, Live/Fixture badge, paints `Presentation`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` `dependencies`, add `"streamlit-shadcn-ui>=1.0.0"` after streamlit.

Run: `uv sync`

Expected: lockfile updates; import `streamlit_shadcn_ui` succeeds.

- [ ] **Step 2: Write `.streamlit/config.toml`**

```toml
[client]
toolbarMode = "minimal"

[theme]
base = "dark"
primaryColor = "#3b82f6"
backgroundColor = "#0b0d10"
secondaryBackgroundColor = "#181a1f"
textColor = "#e8eaed"
borderColor = "#2a2e35"
linkColor = "#3b82f6"
redColor = "#ef4444"
greenColor = "#22c55e"
baseRadius = "none"
buttonRadius = "none"
showWidgetBorder = true
dataframeHeaderBackgroundColor = "#12141a"
font = "Inter:https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap"
headingFont = "Inter:https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap"
```

No test for CSS. This file is required for Task 3’s visual contract.

- [ ] **Step 3: Write the failing shell test (form submit + collapsed sidebar + cache)**

Replace `tests/test_app.py` with a fake that supports `form`, `form_submit_button`, `spinner`, `columns`, `markdown`, `caption`, and records `set_page_config` kwargs:

```python
"""Streamlit submission and cached-result behavior."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent import app
from financial_analyst_agent.config import AppMode
from financial_analyst_agent.turn import Intent, RendererKind, TurnResult


class _Sidebar:
    def toggle(self, *args: Any, **kwargs: Any) -> bool:
        return True


class _Streamlit:
    def __init__(self) -> None:
        self.sidebar = _Sidebar()
        self.session_state: dict[str, object] = {}
        self._button_values = iter((True, False))
        self.page_config: dict[str, Any] = {}

    def set_page_config(self, *args: Any, **kwargs: Any) -> None:
        self.page_config = kwargs

    def title(self, *args: Any, **kwargs: Any) -> None:
        return None

    def warning(self, *args: Any, **kwargs: Any) -> None:
        return None

    def caption(self, *args: Any, **kwargs: Any) -> None:
        return None

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        return None

    def error(self, *args: Any, **kwargs: Any) -> None:
        return None

    def info(self, *args: Any, **kwargs: Any) -> None:
        return None

    def dataframe(self, *args: Any, **kwargs: Any) -> None:
        return None

    @contextmanager
    def form(self, *args: Any, **kwargs: Any):
        yield None

    def text_input(self, *args: Any, **kwargs: Any) -> str:
        return "What was Google's net income?"

    def form_submit_button(self, *args: Any, **kwargs: Any) -> bool:
        return next(self._button_values)

    def button(self, *args: Any, **kwargs: Any) -> bool:
        raise AssertionError("Ask must use st.form_submit_button, not st.button")

    @contextmanager
    def spinner(self, *args: Any, **kwargs: Any):
        yield None

    @contextmanager
    def expander(self, *args: Any, **kwargs: Any):
        yield None

    def columns(self, spec: Any) -> list[Any]:
        return [self, self]


def test_main_runs_only_on_submit_and_renders_cached_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    calls: list[str] = []
    rendered: list[TurnResult] = []

    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(app_mode=AppMode.FIXTURE),
    )
    monkeypatch.setattr(app, "runtime_for_kill_switch", lambda **kwargs: object())

    def fake_run_turn(query: str, runtime: object) -> TurnResult:
        calls.append(query)
        return result

    monkeypatch.setattr(app, "run_turn", fake_run_turn)
    monkeypatch.setattr(app, "render_turn_result", rendered.append)

    app.main()
    app.main()

    assert fake_streamlit.page_config.get("initial_sidebar_state") == "collapsed"
    assert calls == ["What was Google's net income?"]
    assert rendered == [result, result]
```

- [ ] **Step 4: Run the shell test to verify it fails**

Run: `uv run pytest tests/test_app.py -v`

Expected: FAIL (`Ask must use st.form_submit_button` or `AttributeError: form`) because `app.py` still uses `st.button`.

- [ ] **Step 5: Rewrite `app.py` to the shell + presentation renderer**

Replace `src/financial_analyst_agent/app.py` with:

```python
"""One Streamlit window: query, intent chip, tool cards, answer."""

import streamlit as st
import streamlit_shadcn_ui as ui

from financial_analyst_agent.config import AppMode, get_settings
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.presentation import (
    DisplayTable,
    Presentation,
    QuarterlyFactCard,
    metric_legend,
    present_turn,
)
from financial_analyst_agent.runtime import runtime_for_kill_switch
from financial_analyst_agent.turn import RendererKind, TurnResult, run_turn

_GOLD_QUERY = "What was Google's net income based on their latest quarterly report?"
KILL_SWITCH_BANNER = (
    "KILL-SWITCH ON — fixture runtime (recorded facts, not live EDGAR). "
    "Say this out loud. Do not present a cassette as live."
)


def render_turn_result(result: TurnResult) -> None:
    _render_presentation(present_turn(result))


def _render_presentation(presented: Presentation) -> None:
    st.markdown(f"**Intent:** `{presented.intent}`")
    for banner in presented.banners:
        st.info(banner)
    for hit in presented.citations:
        published = f" ({hit.published})" if hit.published else ""
        st.markdown(f"- [{hit.title}]({hit.url}){published}")
    if presented.fact_card is not None:
        _render_fact_card(presented.fact_card)
    if presented.table is not None:
        _render_table(presented.table)
    if presented.message is not None:
        st.error(presented.message)
    if presented.essay is not None:
        st.markdown(presented.essay)
    for trace in presented.traces:
        with st.expander(trace.header, expanded=False):
            for label, value in trace.fields:
                st.markdown(f"**{label}:** {value}")


def _render_fact_card(card: QuarterlyFactCard) -> None:
    ui.metric_card(
        title=card.metric_header,
        content=card.amount,
        description=f"{card.company_name} · {card.ticker}",
        key="lookup-fact",
    )
    st.caption(card.period_label)
    filing = f"[Filing]({card.source_url})" if card.source_url else ""
    st.markdown(
        f"`{card.form}` · `{card.accession_number}` · `{card.concept}` · {filing}"
    )


def _render_table(table: DisplayTable) -> None:
    records = [
        {header: row[index] for index, header in enumerate(table.headers)}
        for row in table.rows
    ]
    st.dataframe(records, use_container_width=True)


def main() -> None:
    st.set_page_config(
        page_title="Financial analyst agent",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    title_col, status_col = st.columns([6, 1])
    with title_col:
        st.title("Financial analyst agent")
    settings = get_settings()
    kill_switch = st.sidebar.toggle(
        "Fixture kill-switch",
        value=settings.app_mode is AppMode.FIXTURE,
        help="Recorded adapters. Announce this if you use it.",
    )
    with status_col:
        ui.badge("Fixture" if kill_switch else "Live", key="runtime-status")
    if kill_switch:
        st.warning(KILL_SWITCH_BANNER)
    else:
        st.caption("Live runtime — SEC XBRL, OpenAI planner, Tavily news.")

    with st.form("ask"):
        query = st.text_input("Ask a question", value=_GOLD_QUERY)
        submitted = st.form_submit_button("Ask", type="primary")
    st.caption(" · ".join(metric_legend()))

    if submitted:
        if st.session_state.get("turn_in_flight"):
            st.info("A turn is already running.")
        else:
            st.session_state["turn_in_flight"] = True
            try:
                with st.spinner("Running turn…"):
                    result = run_turn(query, runtime_for_kill_switch(enabled=kill_switch))
            except ConfigurationError as exc:
                st.error(str(exc))
                st.session_state["turn_in_flight"] = False
                return
            st.session_state["result"] = result
            st.session_state["turn_in_flight"] = False

    if "result" not in st.session_state:
        return
    render_turn_result(st.session_state["result"])


if __name__ == "__main__":
    main()
```

If `ui.badge` in streamlit-shadcn-ui 1.0 is `ui.badge(text="Live")` or `ui.badge("Live", variant="secondary")`, match the installed signature. If `variant` exists, use a success/green variant for Live and a destructive/red variant for Fixture.

`RendererKind` import is unused if you follow the snippet — omit it.

Default `text_input` value on every rerun can reset typed text in some Streamlit versions. Keep `value=_GOLD_QUERY` as the spec’s prefilled gold query. Do not add prompt chips.

- [ ] **Step 6: Run the shell test and presentation tests**

Run: `uv run pytest tests/test_app.py tests/test_presentation.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .streamlit/config.toml src/financial_analyst_agent/app.py tests/test_app.py
git commit -m "Paint formatted turns in a dark Streamlit shell with a collapsed kill-switch."
```

If `uv.lock` is not generated, commit whatever lockfile `uv sync` wrote. Do not commit secrets.

---

### Task 4: Verify gold and types

**Files:**
- None unless a test failed

**Interfaces:**
- Consumes: Tasks 1–3
- Produces: evidence that `run_turn` gold and mypy still pass

- [ ] **Step 1: Run gold**

Run: `uv run pytest -m gold -v`

Expected: PASS, same assertions as before (no gold edits).

- [ ] **Step 2: Run the full offline suite and mypy**

Run: `uv run pytest -q`

Expected: all non-network tests PASS (count may be prior 128 plus new presentation tests).

Run: `uv run mypy`

Expected: Success, no issues.

Run: `uv run ruff check src/financial_analyst_agent/presentation.py src/financial_analyst_agent/app.py tests/test_presentation.py tests/test_app.py`

Expected: All checks passed. Fix any unused imports (`RendererKind` in app.py).

- [ ] **Step 3: Commit only if Step 2 required fixes**

If you had to fix types or unused imports:

```bash
git add src/financial_analyst_agent/app.py src/financial_analyst_agent/presentation.py
git commit -m "Satisfy typecheck after the audience-window renderer."
```

If nothing changed, do not create an empty commit.

---

## Self-review

**Spec coverage**

| Spec requirement | Task |
| --- | --- |
| Compact USD T/B/M, half up, `$112.19 B`, under-$1M grouped, market cap | 1 |
| Margin percent one decimal | 1 |
| Dates `MMM D, YYYY`; datetimes no seconds UTC | 1 |
| Domain-first headers and reasons | 1 |
| `present_turn` fact card, omit empty columns, banners, traces, citations, refuse | 2 |
| Lookup hero not JSON; latest standalone quarter copy | 2 + 3 |
| Rank/compare/rank-and-lookup tables | 2 + 3 |
| News unparseable published string | 2 |
| Metric legend, Ask a question, gold prefill, no chips | 3 |
| Form, spinner, in-flight guard, cache | 3 |
| Collapsed sidebar, kill-switch, Live/Fixture badge, banner | 3 |
| Dark theme, blue primary, hidden Deploy | 3 |
| shadcn metric_card + badge; native dataframe/form/sidebar | 3 |
| Gold / `run_turn` unchanged | 4 |
| No ADR 0002, no historical picker, no CSS tests | out of scope / not tasked |

**Placeholders:** none. **Types:** `Presentation`, `QuarterlyFactCard`, `DisplayTable`, `present_turn`, `format_usd`, `metric_legend` are named the same in Tasks 1–3.
