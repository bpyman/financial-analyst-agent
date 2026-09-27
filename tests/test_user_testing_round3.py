"""Third round of user testing: conversations replayed on the recorded runtime.

Each test is a conversation a tester had with the public demo, with the answer
it should have got.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from financial_analyst_agent.presentation import Presentation


# Imported per test, and kept out of tests/unit: tests/unit/test_contracts_import
# reloads the conversation modules but not the planner, so a recorded runtime used
# after it carries enum members the reloaded seam does not recognise.
@pytest.fixture
def runtime():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime()


def _conversation(runtime, *messages: str) -> list[Presentation]:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.presentation import present_turn
    from financial_analyst_agent.runtime import RuntimeKind
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    store = EphemeralThreadStore()
    thread_id = uuid.uuid4().hex
    start_thread(thread_id, RuntimeKind.RECORDED, store=store)
    return [
        present_turn(run_conversation_turn(thread_id, message, runtime, store=store).result)
        for message in messages
    ]


def _tickers(answer: Presentation) -> set[str]:
    if answer.fact_card is not None:
        return {answer.fact_card.ticker}
    assert answer.table is not None, answer.message
    column = answer.table.headers.index("Ticker")
    return {row[column] for row in answer.table.rows}


def test_a_period_question_naming_another_company_answers_that_company(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(
        runtime,
        "Apple revenue last 4 quarters",
        "Microsoft TTM net income",
        "calendar Q2 2026 revenue for Oracle",
    )
    assert _tickers(answers[0]) == {"AAPL"}
    assert _tickers(answers[1]) == {"MSFT"}
    assert _tickers(answers[2]) == {"ORCL"}


def test_a_company_named_after_a_ranking_replaces_the_ranking(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(
        runtime,
        "Rank the top 5 banks by net income",
        "JPMorgan diluted EPS last 4 quarters",
    )
    assert answers[0].table is not None and "Rank" in answers[0].table.headers
    assert _tickers(answers[1]) == {"JPM"}
    assert answers[1].table is not None and "Rank" not in answers[1].table.headers
    assert len(answers[1].table.rows) == 4


def test_a_period_on_its_own_still_edits_the_current_analysis(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(runtime, "Apple revenue", "last 4 quarters")
    assert _tickers(answers[1]) == {"AAPL"}
    assert answers[1].table is not None and len(answers[1].table.rows) == 4


@pytest.mark.parametrize(
    ("question", "name"),
    [
        ("Costco revenue", "Costco Wholesale"),
        ("COST revenue", "Costco Wholesale"),
        ("Compare Apple and Walmart revenue", "Walmart"),
    ],
)
def test_a_company_the_demo_did_not_record_is_named_not_swapped(
    runtime, question: str, name: str
) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(runtime, "Tesla vs GM revenue", question)
    reply = answers[1]
    assert reply.table is None and reply.fact_card is None
    assert reply.message is not None
    assert reply.message.startswith(f"{name} isn't in the recorded demo")
    assert reply.message_tone == "info"


def test_a_recorded_company_is_not_mistaken_for_a_missing_one(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(runtime, "Apple revenue", "what about AMD?")
    assert _tickers(answers[1]) == {"AMD"}


def test_no_company_named_says_so_instead_of_unknown(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = _conversation(runtime, "revenue please")
    assert answers[0].message is not None
    assert "unknown" not in answers[0].message
    assert answers[0].message.startswith("I couldn't tell which company you mean")
