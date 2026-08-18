"""Gold: top 10 healthcare from the checked-in universe snapshot through run_turn."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import DemoCompleter, fixture_runtime
from financial_analyst_agent.turn import Intent, RendererKind, Runtime, run_turn
from financial_analyst_agent.universe import UniverseCompany, build_universe_snapshot

HEALTHCARE_TOP_10_QUERY = "What are the top 10 companies in healthcare?"

SNAPSHOT_AS_OF = "2026-08-17T16:00:00+00:00"

# Fixture-runtime gold literals (checked-in snapshot, not a live screener).
HEALTHCARE_TOP_10 = (
    ("Eli Lilly and Company", "LLY", "0000059478", Decimal("800000000000")),
    ("UnitedHealth Group Incorporated", "UNH", "0000731766", Decimal("500000000000")),
    ("Johnson & Johnson", "JNJ", "0000200406", Decimal("395000000000")),
    ("AbbVie Inc.", "ABBV", "0001551152", Decimal("330000000000")),
    ("Merck & Co., Inc.", "MRK", "0000310158", Decimal("280000000000")),
    ("Thermo Fisher Scientific Inc.", "TMO", "0000097745", Decimal("210000000000")),
    ("Abbott Laboratories", "ABT", "0000001800", Decimal("195000000000")),
    ("Danaher Corporation", "DHR", "0000313616", Decimal("175000000000")),
    ("Amgen Inc.", "AMGN", "0000318154", Decimal("155000000000")),
    ("Pfizer Inc.", "PFE", "0000078003", Decimal("140000000000")),
)


def test_run_turn_returns_rank_table_for_top_10_healthcare() -> None:
    result = run_turn(HEALTHCARE_TOP_10_QUERY, fixture_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert result.banners == [f"Universe snapshot as of {SNAPSHOT_AS_OF}"]
    assert result.numeral_lock_extras == []
    assert result.message is None

    assert len(result.tool_traces) == 1
    trace = result.tool_traces[0]
    assert trace.tool == "rank_companies"
    assert trace.args == {"industry": "healthcare", "limit": 10}
    assert trace.provenance["snapshot_as_of"] == SNAPSHOT_AS_OF
    assert trace.provenance["source"] == "universe_snapshot"

    assert len(result.table_rows) == 10
    tickers = [row.ticker for row in result.table_rows]
    assert "GILD" not in tickers
    assert "XLV" not in tickers
    assert tickers.count("UNH") == 1
    for index, (name, ticker, cik, market_cap) in enumerate(HEALTHCARE_TOP_10, start=1):
        row = result.table_rows[index - 1]
        assert row.rank == index
        assert row.company_name == name
        assert row.ticker == ticker
        assert row.cik == cik
        assert row.metric == "market_cap"
        assert row.value == market_cap
        assert row.currency == "USD"
        assert row.reason is None


UNKNOWN_INDUSTRY_QUERY = "What are the top 10 companies in AI?"
ALLOWED_INDUSTRIES = ("finance", "healthcare", "technology")


def test_run_turn_refuses_unknown_ai_industry_with_allowed_names() -> None:
    result = run_turn(UNKNOWN_INDUSTRY_QUERY, fixture_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.REFUSE
    assert result.table_rows == []
    assert result.tool_traces == []
    assert result.numeral_lock_extras == []
    assert result.message is not None
    assert "ai" in result.message.casefold()
    for industry in ALLOWED_INDUSTRIES:
        assert industry in result.message.casefold()


FINANCE_TOP_10_QUERY = "What are the top 10 companies in finance?"
FINANCE_TOP_4 = (
    ("JPMorgan Chase & Co.", "JPM", "0000019617", Decimal("600000000000")),
    ("Bank of America Corporation", "BAC", "0000070858", Decimal("300000000000")),
    ("Wells Fargo & Company", "WFC", "0000072971", Decimal("200000000000")),
    ("The Goldman Sachs Group, Inc.", "GS", "0000886982", Decimal("150000000000")),
)


def test_run_turn_ranks_finance_alias_and_does_not_pad_short_sectors() -> None:
    result = run_turn(FINANCE_TOP_10_QUERY, fixture_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert len(result.table_rows) == 4
    assert len(result.table_rows) < 10
    for index, (name, ticker, cik, market_cap) in enumerate(FINANCE_TOP_4, start=1):
        row = result.table_rows[index - 1]
        assert row.rank == index
        assert row.company_name == name
        assert row.ticker == ticker
        assert row.cik == cik
        assert row.value == market_cap
        assert row.reason is None


TECHNOLOGY_TOP_10_QUERY = "What are the top 10 companies in technology?"
TECHNOLOGY_TOP_3 = (
    ("Apple Inc.", "AAPL", "0000320193", Decimal("3500000000000")),
    ("Microsoft Corporation", "MSFT", "0000789019", Decimal("3100000000000")),
    ("Alphabet Inc.", "GOOG", "0001652044", Decimal("2200000000000")),
)


def test_run_turn_ranks_technology_and_consolidates_share_classes() -> None:
    result = run_turn(TECHNOLOGY_TOP_10_QUERY, fixture_runtime())

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    assert len(result.table_rows) == 3
    ciks = [row.cik for row in result.table_rows]
    assert ciks.count("0001652044") == 1
    tickers = [row.ticker for row in result.table_rows]
    assert "GOOGL" not in tickers
    for index, (name, ticker, cik, market_cap) in enumerate(TECHNOLOGY_TOP_3, start=1):
        row = result.table_rows[index - 1]
        assert row.rank == index
        assert row.company_name == name
        assert row.ticker == ticker
        assert row.cik == cik
        assert row.value == market_cap


class _ExplodingFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        raise AssertionError("rank must not call fact lookup")


def _company(
    *,
    cik: str,
    name: str,
    ticker: str,
    market_cap: str,
    sector: str = "Healthcare",
    exchange: str = "NYSE",
    is_etf: bool = False,
    is_fund: bool = False,
) -> UniverseCompany:
    return UniverseCompany(
        cik=cik,
        name=name,
        ticker=ticker,
        sector=sector,
        exchange=exchange,
        market_cap=Decimal(market_cap),
        is_etf=is_etf,
        is_fund=is_fund,
    )


def test_run_turn_ranks_builder_snapshot_without_etfs_funds_or_duplicate_ciks() -> None:
    snapshot = build_universe_snapshot(
        (
            _company(
                cik="0000731766",
                name="UnitedHealth Group Incorporated",
                ticker="UNH",
                market_cap="500000000000",
            ),
            _company(
                cik="0000731766",
                name="UnitedHealth Group Incorporated",
                ticker="UNHC",
                market_cap="499000000000",
            ),
            _company(
                cik="0000059478",
                name="Eli Lilly and Company",
                ticker="LLY",
                market_cap="800000000000",
            ),
            _company(
                cik="0000884394",
                name="Health Care Select Sector SPDR Fund",
                ticker="XLV",
                market_cap="900000000000",
                is_etf=True,
            ),
            _company(
                cik="0000102909",
                name="Vanguard Health Care Fund",
                ticker="VGHCX",
                market_cap="850000000000",
                is_fund=True,
            ),
            _company(
                cik="0000999999",
                name="Pink Sheet Health Co.",
                ticker="OTCH",
                market_cap="700000000000",
                exchange="OTC",
            ),
        ),
        as_of=datetime(2026, 8, 17, 16, 0, tzinfo=UTC),
    )
    result = run_turn(
        HEALTHCARE_TOP_10_QUERY,
        Runtime(
            completer=DemoCompleter(),
            facts=_ExplodingFacts(),
            ranking=SnapshotRanking(snapshot),
        ),
    )

    assert result.intent is Intent.RANK
    assert result.renderer is RendererKind.TABLE
    tickers = [row.ticker for row in result.table_rows]
    assert tickers == ["LLY", "UNH"]
    assert "XLV" not in tickers
    assert "VGHCX" not in tickers
    assert "UNHC" not in tickers
    assert "OTCH" not in tickers
    assert [row.cik for row in result.table_rows].count("0000731766") == 1

