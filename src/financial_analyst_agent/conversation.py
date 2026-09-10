"""Conversation seam: thread identifier + analyst message + runtime → typed turn.

Persistence is delegated to a ThreadStore. Run state stays ephemeral inside
the turn (proposed patch, compiled tasks) and is never written to the store.
Evidence bodies live in the store's EvidenceStore; thread state keeps refs.

Pending clarification is thread state: an ambiguous metric or ambiguous
extend/replace scope holds the planned patch until the analyst answers or
asks something unrelated (which discards it explicitly).
"""

from __future__ import annotations

import inspect
import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from financial_analyst_agent.contracts import RendererKind, Runtime, TurnResult
from financial_analyst_agent.evidence_store import (
    EvidenceCachedFacts,
    grounding_json_from_result,
    label_reused_evidence,
    retain_result_evidence,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.observability import call_provider, timed
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase
from financial_analyst_agent.thread_store import (
    PendingClarification,
    ThreadMessage,
    ThreadState,
    ThreadStore,
)

DISCARDED_CLARIFICATION_BANNER = "Discarded pending clarification"
_REMOVE_METRIC_EDIT = re.compile(
    r"^\s*(?:drop|remove|without)\s+",
    re.IGNORECASE,
)


def _accepts_current_spec(completer: Any) -> bool:
    try:
        params = inspect.signature(completer.complete).parameters
    except (TypeError, ValueError):
        return False
    if "current_spec" in params:
        return True
    return any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values()
    )


def _complete(completer: Any, message: str, current_spec: AnalysisSpec | None) -> Any:
    if _accepts_current_spec(completer):
        return call_provider(
            "planner",
            lambda: completer.complete(message, current_spec=current_spec),
        )
    return call_provider("planner", lambda: completer.complete(message))


class ConversationTurn(BaseModel):
    thread_id: str
    result: TurnResult
    messages: tuple[ThreadMessage, ...] = ()
    results: tuple[TurnResult, ...] = ()
    last_result: TurnResult
    analysis_spec: AnalysisSpec | None = None
    proposed_patch: SpecPatch | None = None


def _match_clarification_answer(
    pending: PendingClarification, message: str
) -> str | None:
    """Return the chosen candidate when the message answers the open question."""
    if pending.kind == "ambiguous_metric":
        resolved = resolve_metric_phrase(message)
        if resolved.kind != "unique":
            return None
        metrics: tuple[str, ...]
        if resolved.metrics:
            metrics = resolved.metrics
        elif resolved.metric is not None:
            metrics = (resolved.metric,)
        else:
            return None
        if len(metrics) != 1:
            return None
        chosen = metrics[0]
        if chosen not in pending.candidates:
            return None
        return chosen
    if pending.kind == "ambiguous_mode":
        text = message.strip().casefold()
        for candidate in pending.candidates:
            if text == candidate.casefold():
                return candidate
        return None
    return None


def _pending_from_clarify(
    result: TurnResult, patch: SpecPatch, message: str = ""
) -> PendingClarification | None:
    if result.renderer is not RendererKind.CLARIFY or not result.candidates:
        return None
    kind: Literal["ambiguous_metric", "ambiguous_mode"] = (
        "ambiguous_mode"
        if result.candidates == ("extend", "replace")
        else "ambiguous_metric"
    )
    metric_role: Literal["add", "remove"] = (
        "remove" if _REMOVE_METRIC_EDIT.match(message.strip()) else "add"
    )
    return PendingClarification(
        kind=kind,
        candidates=result.candidates,
        patch=patch,
        intent=result.intent,
        metric_role=metric_role,
    )


def _resume_pending(
    pending: PendingClarification,
    answer: str,
    message: str,
    runtime: Runtime,
    *,
    current_spec: AnalysisSpec | None,
    on_progress: Any | None,
    max_workers: int,
) -> tuple[TurnResult, AnalysisSpec | None, SpecPatch]:
    from financial_analyst_agent.graph.spec_turn import run_spec_turn

    if pending.kind == "ambiguous_metric":
        if pending.metric_role == "remove":
            patch = pending.patch.model_copy(
                update={"remove_metrics": (answer,), "add_metrics": ()}
            )
        else:
            patch = pending.patch.model_copy(update={"add_metrics": (answer,)})
        if patch.mode is None and current_spec is None:
            patch = patch.model_copy(update={"mode": "replace"})
        return run_spec_turn(
            message,
            runtime,
            current_spec=current_spec,
            proposal=patch,
            on_progress=on_progress,
            max_workers=max_workers,
        )
    # ambiguous_mode
    mode: Literal["extend", "replace"] = "extend" if answer == "extend" else "replace"
    patch = pending.patch.model_copy(update={"mode": mode})
    return run_spec_turn(
        message,
        runtime,
        current_spec=current_spec,
        proposal=patch,
        on_progress=on_progress,
        max_workers=max_workers,
    )


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
        is_filing_change_proposal,
        is_qualitative_proposal,
        is_structured_proposal,
        run_spec_turn,
    )

    finish = timed("conversation_turn", thread_id=thread_id)
    prior = store.load(thread_id) or ThreadState(thread_id=thread_id)
    workers = DEFAULT_TASK_MAX_WORKERS if max_workers is None else max_workers

    evidence = store.evidence_for(thread_id)
    prior_ids = evidence.known_ids()
    cached_facts = EvidenceCachedFacts(
        runtime.facts, evidence, prior_ids=prior_ids
    )
    turn_runtime = replace(runtime, facts=cached_facts)

    proposed_patch: SpecPatch | None = None
    analysis_spec: AnalysisSpec | None = None
    persist_spec: AnalysisSpec | None = prior.analysis_spec
    pending_out: PendingClarification | None = None
    discarded_clarification = False

    resumed = False
    if prior.pending_clarification is not None:
        answer = _match_clarification_answer(prior.pending_clarification, message)
        if answer is not None:
            result, new_spec, proposed_patch = _resume_pending(
                prior.pending_clarification,
                answer,
                message,
                turn_runtime,
                current_spec=prior.analysis_spec,
                on_progress=on_progress,
                max_workers=workers,
            )
            if new_spec is not None:
                analysis_spec = new_spec
                persist_spec = new_spec
            else:
                analysis_spec = None
                persist_spec = prior.analysis_spec
            pending_out = _pending_from_clarify(result, proposed_patch, message)
            resumed = True
        else:
            discarded_clarification = True

    if not resumed:
        proposal: Any = _complete(runtime.completer, message, prior.analysis_spec)

        if is_filing_change_proposal(proposal):
            result = run_workflow_turn(
                proposal,
                turn_runtime,
                query=message,
            )
            persist_spec = prior.analysis_spec
            analysis_spec = prior.analysis_spec
        elif is_qualitative_proposal(proposal):
            prior_result = store.resolve_last_result(prior)
            result = run_workflow_turn(
                proposal,
                turn_runtime,
                query=message,
                grounding_json=grounding_json_from_result(prior_result),
            )
            persist_spec = None
            analysis_spec = None
        elif is_structured_proposal(proposal):
            result, new_spec, proposed_patch = run_spec_turn(
                message,
                turn_runtime,
                current_spec=prior.analysis_spec,
                proposal=proposal,
                on_progress=on_progress,
                max_workers=workers,
            )
            pending_from_result = _pending_from_clarify(
                result, proposed_patch, message
            )
            if pending_from_result is not None:
                pending_out = pending_from_result
                analysis_spec = None
                persist_spec = prior.analysis_spec
            elif new_spec is not None:
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

    if discarded_clarification:
        banners = list(result.banners)
        if DISCARDED_CLARIFICATION_BANNER not in banners:
            banners.append(DISCARDED_CLARIFICATION_BANNER)
        result = result.model_copy(update={"banners": banners})

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
        pending_clarification=pending_out,
        turn_count=prior.turn_count + 1,
        live_sec_requests=prior.live_sec_requests,
        updated_at=datetime.now(UTC),
    )
    store.save(state)
    prior_results = store.resolve_results(
        ThreadState(
            thread_id=thread_id,
            messages=prior.messages,
            evidence_refs=prior.evidence_refs,
            last_result_ref=prior.last_result_ref,
            analysis_spec=prior.analysis_spec,
            pending_clarification=prior.pending_clarification,
        )
    )
    results = (*prior_results, result)
    finish(
        turn=state.turn_count,
        intent=result.intent.value,
        renderer=result.renderer.value,
    )
    return ConversationTurn(
        thread_id=thread_id,
        result=result,
        messages=messages,
        results=results,
        last_result=result,
        analysis_spec=analysis_spec,
        proposed_patch=proposed_patch,
    )
