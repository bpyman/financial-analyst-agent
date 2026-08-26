"""Conversation seam: thread identifier + analyst message + runtime → typed turn.

Persistence is delegated to a ThreadStore. Run state stays ephemeral inside
``execute_turn`` and is never written to the store.
"""

from __future__ import annotations

from pydantic import BaseModel

from financial_analyst_agent.contracts import Runtime, TurnResult
from financial_analyst_agent.thread_store import (
    ThreadMessage,
    ThreadState,
    ThreadStore,
)


class ConversationTurn(BaseModel):
    thread_id: str
    result: TurnResult
    messages: tuple[ThreadMessage, ...] = ()
    last_result: TurnResult


def run_conversation_turn(
    thread_id: str,
    message: str,
    runtime: Runtime,
    *,
    store: ThreadStore,
) -> ConversationTurn:
    """Run one analyst message on a conversation thread and persist thread state."""
    from financial_analyst_agent.turn import execute_turn

    prior = store.load(thread_id) or ThreadState(thread_id=thread_id)
    result = execute_turn(message, runtime)
    messages = (*prior.messages, ThreadMessage(role="analyst", content=message))
    state = ThreadState(thread_id=thread_id, messages=messages, last_result=result)
    store.save(state)
    return ConversationTurn(
        thread_id=thread_id,
        result=result,
        messages=messages,
        last_result=result,
    )
