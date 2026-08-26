"""Conversation seam: thread identifier + analyst message + runtime → typed turn.

Persistence is delegated to a ThreadStore. Run state stays ephemeral inside
the turn (proposed patch, compiled tasks) and is never written to the store.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from financial_analyst_agent.contracts import Runtime, TurnResult
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.thread_store import (
    ThreadMessage,
    ThreadState,
    ThreadStore,
)


class ConversationTurn(BaseModel):
    thread_id: str
    result: TurnResult
    messages: tuple[ThreadMessage, ...] = ()
    results: tuple[TurnResult, ...] = ()
    last_result: TurnResult
    analysis_spec: AnalysisSpec | None = None
    proposed_patch: SpecPatch | None = None


def run_conversation_turn(
    thread_id: str,
    message: str,
    runtime: Runtime,
    *,
    store: ThreadStore,
    on_progress: Any | None = None,
    max_workers: int | None = None,
) -> ConversationTurn:
    """Run one analyst message on a conversation thread and persist thread state.

    ``on_progress(done, total)`` is invoked as independent compiled cells finish.
    ``max_workers`` caps concurrent provider fan-out for structured analyses.
    """
    from financial_analyst_agent.graph import run_workflow_turn
    from financial_analyst_agent.graph.spec_turn import (
        DEFAULT_TASK_MAX_WORKERS,
        is_qualitative_proposal,
        is_structured_proposal,
        run_spec_turn,
    )

    prior = store.load(thread_id) or ThreadState(thread_id=thread_id)
    proposal: Any = runtime.completer.complete(message)

    proposed_patch: SpecPatch | None = None
    analysis_spec: AnalysisSpec | None = None
    persist_spec: AnalysisSpec | None = prior.analysis_spec
    workers = DEFAULT_TASK_MAX_WORKERS if max_workers is None else max_workers

    if is_qualitative_proposal(proposal):
        result = run_workflow_turn(proposal, runtime, query=message)
        persist_spec = None
    elif is_structured_proposal(proposal):
        result, new_spec, proposed_patch = run_spec_turn(
            message,
            runtime,
            current_spec=prior.analysis_spec,
            proposal=proposal,
            on_progress=on_progress,
            max_workers=workers,
        )
        if new_spec is not None:
            analysis_spec = new_spec
            persist_spec = new_spec
        else:
            analysis_spec = None
            persist_spec = prior.analysis_spec
    else:
        from financial_analyst_agent.turn import execute_turn

        result = execute_turn(message, runtime)
        analysis_spec = prior.analysis_spec
        persist_spec = prior.analysis_spec

    messages = (*prior.messages, ThreadMessage(role="analyst", content=message))
    results = (*prior.results, result)
    state = ThreadState(
        thread_id=thread_id,
        messages=messages,
        results=results,
        last_result=result,
        analysis_spec=persist_spec,
    )
    store.save(state)
    return ConversationTurn(
        thread_id=thread_id,
        result=result,
        messages=messages,
        results=results,
        last_result=result,
        analysis_spec=analysis_spec,
        proposed_patch=proposed_patch,
    )
