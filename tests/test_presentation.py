from datetime import date, datetime, timezone
from decimal import Decimal

from financial_analyst_agent.presentation import (
    format_date,
    format_datetime_utc,
    format_field_name,
    format_metric_value,
    format_percent,
    format_reason,
    format_usd,
    try_parse_datetime,
)


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
