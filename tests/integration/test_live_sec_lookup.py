"""Optional live SEC lookup through run_turn. Skipped in the default suite."""

from datetime import timedelta
from decimal import Decimal

import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.news import TavilyNewsSearch
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import DemoCompleter, FixtureEssayCompleter
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.turn import Intent, RendererKind, Runtime, RuntimeKind, run_turn
from test_run_turn_lookup import GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY

ALPHABET_CIK = "0001652044"
ALPHABET_NAME = "Alphabet Inc."


@pytest.mark.network
def test_run_turn_live_sec_lookup_google_net_income() -> None:
    settings = Settings()
    if not settings.sec_user_agent.strip():
        pytest.skip("SEC_USER_AGENT required for live SEC")

    result = run_turn(
        GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY,
        Runtime(
            completer=DemoCompleter(),
            facts=SecFactLookup(settings),
            ranking=SnapshotRanking.from_path(),
            news=TavilyNewsSearch(settings),
            essay=FixtureEssayCompleter(),
            kind=RuntimeKind.LIVE,
        ),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.tool_traces[0].tool == "get_financials"
    assert result.tool_traces[0].args == {"company": "Google", "metric": "net_income"}

    row = result.table_rows[0]
    assert row.company_name == ALPHABET_NAME
    assert row.cik == ALPHABET_CIK
    assert row.ticker in {"GOOG", "GOOGL"}
    assert row.metric == "net_income"
    assert isinstance(row.value, Decimal)
    assert row.value > 0
    assert row.currency == "USD"
    assert row.form in {"10-Q", "10-Q/A"}
    assert row.taxonomy == "us-gaap"
    assert row.concept in {"NetIncomeLoss", "ProfitLoss"}
    assert row.accession_number
    assert "sec.gov" in row.source_url
    assert 70 <= (row.end_date - row.start_date).days <= 110
    assert row.end_date - row.start_date <= timedelta(days=110)
    assert result.tool_traces[0].provenance["accession_number"] == row.accession_number
    assert result.tool_traces[0].provenance["source_url"] == row.source_url
    assert result.tool_traces[0].provenance["concept"] == row.concept
    assert result.tool_traces[0].provenance["start_date"] == row.start_date.isoformat()
    assert result.tool_traces[0].provenance["end_date"] == row.end_date.isoformat()
