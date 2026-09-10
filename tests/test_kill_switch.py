"""Kill-switch selects fixture vs live runtime; Streamlit uses one TurnResult renderer."""

from financial_analyst_agent.turn import Intent, RendererKind, run_turn
from test_run_turn_lookup import ACCESSION, GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, NET_INCOME


def test_kill_switch_on_replays_recorded_google_net_income() -> None:
    from financial_analyst_agent.runtime import runtime_for_kill_switch

    result = run_turn(
        GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY,
        runtime_for_kill_switch(enabled=True),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.table_rows[0].value == NET_INCOME
    assert result.table_rows[0].accession_number == ACCESSION


def test_kill_switch_banner_discloses_recorded_data() -> None:
    from financial_analyst_agent.app import KILL_SWITCH_BANNER

    text = KILL_SWITCH_BANNER.casefold()
    assert "recorded" in text
    assert "edgar" in text or "live" in text
