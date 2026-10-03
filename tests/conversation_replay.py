"""Replay a conversation on a runtime and read its answers back.

The application imports stay inside the functions: tests/unit/test_contracts_import
reloads the conversation modules, and a module imported before that would keep
enum members the reloaded seam does not recognise.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from financial_analyst_agent.contracts import Runtime, TurnResult
    from financial_analyst_agent.presentation import Presentation
    from financial_analyst_agent.thread_store import ThreadState


class Replay(NamedTuple):
    """Each answer, the final chips, and whether a clarification is pending."""

    answers: list[Presentation]
    chips: tuple[str, ...]
    pending: bool


def _run(runtime: Runtime, messages: tuple[str, ...]) -> tuple[list[TurnResult], ThreadState]:
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.runtime import RuntimeKind
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    store = EphemeralThreadStore()
    thread_id = uuid.uuid4().hex
    start_thread(thread_id, RuntimeKind.RECORDED, store=store)
    results = [
        run_conversation_turn(thread_id, message, runtime, store=store).result
        for message in messages
    ]
    state = store.load(thread_id)
    assert state is not None
    return results, state


def replay(runtime: Runtime, *messages: str) -> Replay:
    from financial_analyst_agent.presentation import present_turn, spec_chips

    results, state = _run(runtime, messages)
    chips = spec_chips(state.analysis_spec) if state.analysis_spec is not None else ()
    return Replay(
        [present_turn(result) for result in results],
        chips,
        state.pending_clarification is not None,
    )


def ask(runtime: Runtime, *messages: str) -> list[Presentation]:
    return replay(runtime, *messages).answers


def last_result(runtime: Runtime, *messages: str) -> TurnResult:
    """The last turn's result, before it is presented."""
    results, _ = _run(runtime, messages)
    return results[-1]


def column_of(answer: Presentation, header: str) -> list[str]:
    assert answer.table is not None, answer.message
    index = answer.table.headers.index(header)
    return [row[index] for row in answer.table.rows]


def tickers_of(answer: Presentation) -> list[str]:
    """The answer's tickers in the order shown, each once."""
    if answer.fact_card is not None:
        return [answer.fact_card.ticker]
    return list(dict.fromkeys(column_of(answer, "Ticker")))
