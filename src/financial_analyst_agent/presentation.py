from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

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
