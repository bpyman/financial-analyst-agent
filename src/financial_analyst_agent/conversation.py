"""Conversation seam: thread identifier + analyst message + runtime → typed turn.

Persistence is delegated to a ThreadStore. Run state stays ephemeral inside
the turn (proposed patch, compiled tasks) and is never written to the store.
Evidence bodies live in the store's EvidenceStore; thread state keeps refs.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from pydantic import BaseModel

from financial_analyst_agent.contracts import Runtime, TurnResult
from financial_analyst_agent.evidence_store import (
    EvidenceCachedFacts,
    grounding_json_from_result,
    label_reused_evidence,
    retain_result_evidence,
)
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

    evidence = store.evidence_for(thread_id)
    prior_ids = evidence.known_ids()
    cached_facts = EvidenceCachedFacts(
        runtime.facts, evidence, prior_ids=prior_ids
    )
    turn_runtime = replace(runtime, facts=cached_facts)

    if is_qualitative_proposal(proposal):
        prior_result = store.resolve_last_result(prior)
        result = run_workflow_turn(
            proposal,
            turn_runtime,
            query=message,
            grounding_json=grounding_json_from_result(prior_result),
        )
        persist_spec = None
    elif is_structured_proposal(proposal):
        result, new_spec, proposed_patch = run_spec_turn(
            message,
            turn_runtime,
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

        result = execute_turn(message, turn_runtime)
        analysis_spec = prior.analysis_spec
        persist_spec = prior.analysis_spec

    result = label_reused_evidence(result, reused=bool(cached_facts.reused_ids))

    result_ref = retain_result_evidence(evidence, result)
    new_fact_refs = tuple(
        sorted(
            eid
            for eid in evidence.known_ids() - prior_ids
            if eid.startswith("fact-")
        )
    )
    evidence_refs = tuple(
        dict.fromkeys((*prior.evidence_refs, *new_fact_refs, result_ref))
    )

    messages = (*prior.messages, ThreadMessage(role="analyst", content=message))
    state = ThreadState(
        thread_id=thread_id,
        messages=messages,
        evidence_refs=evidence_refs,
        last_result_ref=result_ref,
        analysis_spec=persist_spec,
    )
    store.save(state)
    prior_results = store.resolve_results(
        ThreadState(
            thread_id=thread_id,
            messages=prior.messages,
            evidence_refs=prior.evidence_refs,
            last_result_ref=prior.last_result_ref,
            analysis_spec=prior.analysis_spec,
        )
    )
    results = (*prior_results, result)
    return ConversationTurn(
        thread_id=thread_id,
        result=result,
        messages=messages,
        results=results,
        last_result=result,
        analysis_spec=analysis_spec,
        proposed_patch=proposed_patch,
    )
