from datetime import UTC, date, datetime
from decimal import Decimal

from financial_analyst_agent.presentation import (
    format_date,
    format_datetime_utc,
    format_field_name,
    format_metric_value,
    format_percent,
    format_reason,
    format_usd,
    metric_groups,
    metric_legend,
    present_turn,
    try_parse_datetime,
)
from financial_analyst_agent.turn import (
    Intent,
    NewsHit,
    RendererKind,
    TableRow,
    ToolTrace,
    TurnResult,
)


def test_format_usd_billions_half_up() -> None:
    assert format_usd(Decimal("112193000000")) == "$112.19 B"


def test_format_usd_compact_tie_rounds_half_up() -> None:
    assert format_usd(Decimal("1005000")) == "$1.01 M"
    assert format_usd(Decimal("112195000000")) == "$112.20 B"


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
    stamp = datetime(2026, 8, 17, 16, 0, 0, tzinfo=UTC)
    assert format_datetime_utc(stamp) == "Aug 17, 2026, 4:00 PM UTC"


def test_format_datetime_utc_converts_offset_and_drops_microseconds() -> None:
    stamp = datetime.fromisoformat("2026-08-18T05:10:30.074615-04:00")
    assert format_datetime_utc(stamp) == "Aug 18, 2026, 9:10 AM UTC"


def test_format_percent_one_decimal_half_up() -> None:
    ratio = Decimal("38398000000") / Decimal("82886000000")
    assert format_percent(ratio) == "46.3%"


def test_format_percent_tie_rounds_half_up() -> None:
    assert format_percent(Decimal("0.46350")) == "46.4%"


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
    assert card.metric_header == "Net income"
    assert card.amount == "$62.58 B"
    assert (
        card.period_label
        == "Latest standalone quarter · Jan 1, 2026 – Mar 31, 2026"
    )
    assert card.form == "10-Q"
    assert card.accession_number == "0001652044-26-000048"
    assert card.concept == "NetIncomeLoss"
    assert card.source_url.endswith("goog-20260331.htm")
    trace = presented.traces[0]
    assert dict(trace.inputs) == {
        "Company": "Google",
        "Metric": "net_income",
    }
    outputs = dict(trace.outputs)
    assert outputs["Accession number"] == "0001652044-26-000048"
    assert outputs["Concept"] == "NetIncomeLoss"
    assert outputs["Start date"] == "Jan 1, 2026"
    assert outputs["End date"] == "Mar 31, 2026"
    assert "source_url" not in outputs
    assert all("(" not in label and "_" not in label for label, _ in trace.inputs)
    assert all("(" not in label and "_" not in label for label, _ in trace.outputs)


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
    assert presented.banners == (
        "Universe snapshot as of Aug 17, 2026, 4:00 PM UTC",
    )


def test_present_compare_formats_percent_and_keeps_reason() -> None:
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={
                    "issuers": ["Microsoft", "Google"],
                    "metric": "operating_margin",
                },
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
            NewsHit(
                title="Hit",
                url="https://example.com/n",
                published="yesterday morning",
            )
        ],
        tool_traces=[ToolTrace(tool="search_news", args={"query": "NVIDIA"})],
    )
    presented = present_turn(result)
    assert presented.citations[0].published == "yesterday morning"
    assert presented.essay == "Supply chain remains tight."
    assert presented.table is None
    assert presented.fact_card is None


def test_present_news_formats_date_only_published() -> None:
    result = TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="Supply chain remains tight.",
        citations=[
            NewsHit(
                title="Hit",
                url="https://example.com/n",
                published="2026-01-01",
            )
        ],
        tool_traces=[ToolTrace(tool="search_news", args={"query": "NVIDIA"})],
    )
    presented = present_turn(result)
    assert presented.citations[0].published == "Jan 1, 2026"


def test_present_trace_formats_nested_news_hits_as_readable_lines() -> None:
    result = TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="Supply chain remains tight.",
        tool_traces=[
            ToolTrace(
                tool="search_news",
                args={"query": "NVIDIA"},
                provenance={
                    "hits": [
                        {
                            "title": "First hit",
                            "url": "https://example.com/first",
                            "published": "2026-01-01",
                        },
                        {
                            "title": "Second hit",
                            "url": "https://example.com/second",
                            "published": "yesterday morning",
                        },
                    ]
                },
            )
        ],
    )

    hits = dict(present_turn(result).traces[0].outputs)["Hits"]

    assert hits == (
        "- Title: First hit\n"
        "  Url: https://example.com/first\n"
        "  Published: Jan 1, 2026\n"
        "- Title: Second hit\n"
        "  Url: https://example.com/second\n"
        "  Published: yesterday morning"
    )


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
    assert legend[0] == "Revenue"
    assert "Cost of revenue" in legend
    assert "Operating margin" in legend
    assert all("(" not in name and "_" not in name for name in legend)
    assert len(legend) == 9


def test_metric_groups_split_reported_from_margins() -> None:
    groups = dict(metric_groups())
    assert groups["Reported"][0] == "Revenue"
    assert "Net income" in groups["Reported"]
    assert groups["Margins"] == ("Gross margin", "Operating margin", "Net margin")
