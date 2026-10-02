"""P/E, return on equity, EBITDA, share price, cash and dividends on the recorded demo,
and the round-4 open items that came with them (ADR 0008).

Values are the recorded 27 September 2026 filings and snapshot.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from financial_analyst_agent.presentation import Presentation


# Imported per test, as in test_user_testing_round3.
@pytest.fixture
def runtime():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime()


def _thread(runtime, *messages: str):  # type: ignore[no-untyped-def]
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.presentation import present_turn
    from financial_analyst_agent.runtime import RuntimeKind
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    store = EphemeralThreadStore()
    thread_id = uuid.uuid4().hex
    start_thread(thread_id, RuntimeKind.RECORDED, store=store)
    answers = [
        present_turn(run_conversation_turn(thread_id, message, runtime, store=store).result)
        for message in messages
    ]
    return answers, store.load(thread_id)


def _conversation(runtime, *messages: str) -> list[Presentation]:  # type: ignore[no-untyped-def]
    return _thread(runtime, *messages)[0]


def _column(answer: Presentation, header: str) -> list[str]:
    assert answer.table is not None, answer.message
    index = answer.table.headers.index(header)
    return [row[index] for row in answer.table.rows]


def test_pe_is_market_cap_over_trailing_net_income(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = _conversation(runtime, "Apple P/E")
    assert answer.fact_card is not None
    assert answer.fact_card.amount == "38.9x"
    # Calculated over a trailing year, from the snapshot's market cap and a derived year.
    assert answer.fact_card.period_label == (
        "Calculated † · Trailing year · Jun 29, 2025 – Jun 27, 2026"
    )
    assert answer.fact_card.concept == "Market cap (Sep 27, 2026) ÷ trailing-year net income"
    assert answer.fact_card.form == ""
    assert any("trailing-year net income" in banner for banner in answer.banners)
    labels = [item.label for item in answer.evidence]
    assert "Apple Inc. · Market cap · At Sep 27, 2026" in labels


def test_p_slash_e_is_not_read_as_two_tickers(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = _conversation(runtime, "Compare Nvidia, AMD and Broadcom P/E")
    assert _column(answer, "Ticker") == ["NVDA", "AMD", "AVGO"]
    assert _column(answer, "P/E ratio (trailing year)") == ["28.3x †", "159.8x †", "43.9x †"]


def test_return_on_equity_over_a_window(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = _conversation(runtime, "JPMorgan return on equity last 4 quarters")
    assert _column(answer, "Return on equity (trailing year)") == [
        "17.4% †",
        "16.2% †",
        "15.7%",
        "16.1% †",
    ]
    # A trailing year is not a 52-week quarter.
    assert not any("weeks" in banner for banner in answer.banners)


def test_ebitda_uses_depreciation_plus_amortization_when_no_da_line(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = _conversation(runtime, "Microsoft EBITDA")
    assert answer.fact_card is not None
    assert answer.fact_card.amount == "$51.90 B"
    assert any("depreciation plus amortization" in banner for banner in answer.banners)


def test_dividends_asks_which_and_per_share_answers(runtime) -> None:  # type: ignore[no-untyped-def]
    asked, chosen = _conversation(runtime, "Apple dividends", "per share")
    assert list(asked.candidates) == ["Dividends per share", "Dividends paid"]
    assert chosen.fact_card is not None
    assert (chosen.fact_card.metric_header, chosen.fact_card.amount) == (
        "Dividends per share",
        "$0.27",
    )


def test_share_price_comes_from_the_snapshot(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = _conversation(runtime, "Nvidia stock price")
    assert _column(answer, "Share price") == ["$225.07"]
    assert answer.banners[0].startswith("Universe snapshot as of Sep 27, 2026")


def test_cash_is_a_balance_at_each_quarter_end(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = _conversation(runtime, "Apple cash last 4 quarters")
    assert _column(answer, "Cash and equivalents") == [
        "$39.54 B",
        "$45.57 B",
        "$45.32 B",
        "$35.93 B",
    ]


def test_a_ranking_by_pe_says_what_it_leaves_out(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = _conversation(runtime, "Rank tech companies by P/E")
    assert _column(answer, "Ticker")[:2] == ["AMD", "PLTR"]
    assert any(
        banner.startswith("Ordered by P/E ratio.") and "a higher P/E ratio" in banner
        for banner in answer.banners
    )


# Open items from round 4


def test_a_word_from_one_option_answers_the_clarify(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(runtime, "Apple revenue", "add Google margin", "net")
    assert _column(answers[2], "Ticker") == ["AAPL", "GOOG"]
    assert answers[2].table is not None and "Net margin" in answers[2].table.headers


def test_a_clarified_question_about_another_company_starts_over(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(runtime, "Microsoft revenue", "Apple margin", "2")
    assert answers[2].fact_card is not None
    assert (answers[2].fact_card.ticker, answers[2].fact_card.metric_header) == (
        "AAPL",
        "Operating margin",
    )


def test_a_company_outside_the_snapshot_gets_its_ticker_chip(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.presentation import spec_chips

    _answers, state = _thread(runtime, "Tesla vs GM revenue")
    assert state is not None and state.analysis_spec is not None
    assert spec_chips(state.analysis_spec)[:2] == ("TSLA", "GM")


def test_reusing_fetched_figures_is_not_announced(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(runtime, "Apple revenue", "add net margin")
    assert not any("fetched earlier" in banner for banner in answers[1].banners)
