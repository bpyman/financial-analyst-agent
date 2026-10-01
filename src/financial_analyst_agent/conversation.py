"""Conversation seam: thread identifier + analyst message + runtime → typed turn.

Persistence is delegated to a ThreadStore. Run state stays ephemeral inside
the turn (proposed patch, compiled tasks) and is never written to the store.
Evidence bodies live in the store's EvidenceStore; thread state keeps refs.

Pending clarification is thread state: an ambiguous metric or ambiguous
extend/replace scope holds the planned patch until the analyst answers or
asks something unrelated (which discards it explicitly).

A thread is bound to one runtime (ADR 0006): ``start_thread`` binds it up front,
otherwise its first turn does. A turn on the other runtime raises
``RuntimeMismatchError`` before anything is read from providers or persisted.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from financial_analyst_agent.contracts import RendererKind, Runtime, RuntimeKind, TurnResult
from financial_analyst_agent.domain.errors import RuntimeMismatchError
from financial_analyst_agent.evidence_store import (
    EvidenceCachedFacts,
    grounding_json_from_result,
    label_reused_evidence,
    retain_result_evidence,
    with_banner,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.guide import (
    guide_reply,
    not_recorded_banner,
    not_recorded_reply,
    resets_analysis,
    suggest_follow_ups,
    unrecorded_companies,
)
from financial_analyst_agent.observability import (
    bind_log_context,
    call_provider,
    reset_log_context,
    timed,
)
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase
from financial_analyst_agent.thread_store import (
    PendingClarification,
    ThreadMessage,
    ThreadState,
    ThreadStore,
)

DISCARDED_CLARIFICATION_BANNER = (
    "Answered your new question; the earlier one that needed a choice was set aside."
)
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


_NEW_QUESTION = re.compile(r"\b(?:what|which|how|compare|versus|vs)\b|['’]s\b", re.IGNORECASE)
_MAX_ANSWER_WORDS = 6
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "one": 1, "two": 2, "three": 3}
_ORDINAL_ANSWER = re.compile(
    r"(?:option |number |#)?(\d|first|second|third|fourth|one|two|three)(?: one| option)?"
    r"|(?:the )?(first|second|third|fourth)(?: one| option)?"
)


def _candidate_named_by_word(candidates: tuple[str, ...], message: str) -> str | None:
    """ "net" or "per share" picks the one candidate whose name holds those words."""
    words = set(re.findall(r"[a-z]+", message.casefold()))
    if not words:
        return None
    named = [candidate for candidate in candidates if words <= set(candidate.split("_"))]
    return named[0] if len(named) == 1 else None


def _match_clarification_answer(
    pending: PendingClarification, message: str
) -> str | None:
    """Return the chosen candidate when the message answers the open question."""
    ordinal = _ORDINAL_ANSWER.fullmatch(message.strip().casefold().rstrip(".!"))
    if ordinal is not None:
        # "2" or "the second one" picks from the options as they were shown.
        raw = ordinal.group(1) or ordinal.group(2)
        position = int(raw) if raw.isdigit() else _ORDINAL_WORDS[raw]
        if 1 <= position <= len(pending.candidates):
            return pending.candidates[position - 1]
        return None
    if pending.kind == "ambiguous_metric":
        if _NEW_QUESTION.search(message) or len(message.split()) > _MAX_ANSWER_WORDS:
            # "What was Microsoft's net income?" names a candidate but is a new
            # question; answering the held patch would drop its company.
            return None
        resolved = resolve_metric_phrase(message)
        if resolved.kind != "unique":
            return _candidate_named_by_word(pending.candidates, message)
        metrics = resolved.unique_metrics
        if len(metrics) != 1:
            return None
        chosen = metrics[0]
        if chosen not in pending.candidates:
            # "per share" names EPS on its own, but here it picks dividends per share.
            return _candidate_named_by_word(pending.candidates, message)
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
        question=message,
    )


_ADD_WORDS = re.compile(r"(?:and|also|plus|add|include|with)\b", re.IGNORECASE)


def _resume_pending(
    pending: PendingClarification,
    answer: str,
    message: str,
    runtime: Runtime,
    *,
    current_spec: AnalysisSpec | None,
    on_progress: Callable[[int, int], None] | None,
    max_workers: int,
) -> tuple[TurnResult, AnalysisSpec | None, SpecPatch]:
    from financial_analyst_agent.graph.spec_turn import TurnContext, run_spec_turn_context

    if pending.kind == "ambiguous_metric" and resolve_metric_phrase(message).metric != answer:
        # The turn reads its wording too: "2" or "net" names no one metric, the choice does.
        message = answer.replace("_", " ")
    if pending.kind == "ambiguous_metric":
        if pending.metric_role == "remove":
            patch = pending.patch.model_copy(
                update={"remove_metrics": (answer,), "add_metrics": ()}
            )
        else:
            patch = pending.patch.model_copy(update={"add_metrics": (answer,)})
            if patch.add_companies and not _ADD_WORDS.match(pending.question.strip()):
                # "Apple margin" after Microsoft revenue is a question of its own:
                # the chosen margin replaces revenue rather than joining it.
                patch = patch.model_copy(update={"mode": "replace", "remove_companies": ()})
        if patch.mode is None and current_spec is None:
            patch = patch.model_copy(update={"mode": "replace"})
    else:  # ambiguous_mode: the held question is what the chosen scope answers.
        mode: Literal["extend", "replace"] = "extend" if answer == "extend" else "replace"
        patch = pending.patch.model_copy(update={"mode": mode})
        message = pending.question or message
    return run_spec_turn_context(
        TurnContext(
            message=message,
            current_spec=current_spec,
            proposal=patch,
            on_progress=on_progress,
            max_workers=max_workers,
        ),
        runtime,
    )


_PEER_COUNT = 3


def _with_peers(proposal: Any, ranking: Any) -> Any:
    """Add the largest companies in the named company's industry ("… to its peers")."""
    if getattr(proposal, "peers", False) is not True or not getattr(proposal, "companies", None):
        return proposal
    lookup = getattr(ranking, "lookup_member", None)
    peers = getattr(ranking, "peers", None)
    if not callable(lookup) or not callable(peers):
        return proposal
    try:
        member = lookup(proposal.companies[0])
    except Exception:
        return proposal
    found = peers(member.cik, limit=_PEER_COUNT)
    proposal.companies = [*proposal.companies, *(peer.ticker for peer in found)]
    return proposal


def start_thread(thread_id: str, runtime: RuntimeKind, *, store: ThreadStore) -> ThreadState:
    """Create an empty conversation thread bound to ``runtime`` and persist it."""
    state = ThreadState(thread_id=thread_id, runtime=runtime)
    store.save(state)
    return state


def _check_runtime(prior: ThreadState, runtime: Runtime) -> None:
    if prior.runtime is not None and prior.runtime != runtime.kind:
        raise RuntimeMismatchError(
            f"This thread runs on the {prior.runtime.value} runtime and cannot take "
            f"a {runtime.kind.value} turn. Start over to switch runtime.",
            {"thread": prior.runtime.value, "turn": runtime.kind.value},
        )


def run_conversation_turn(
    thread_id: str,
    message: str,
    runtime: Runtime,
    *,
    store: ThreadStore,
    on_progress: Callable[[int, int], None] | None = None,
    max_workers: int | None = None,
) -> ConversationTurn:
    """Run one analyst message on a conversation thread and persist thread state.

    ``on_progress(done, total)`` is invoked as independent compiled cells finish.
    ``max_workers`` caps concurrent provider fan-out for structured analyses.
    Raises ``RuntimeMismatchError`` when the thread is bound to the other runtime;
    an unbound thread binds to ``runtime.kind``.
    """
    from financial_analyst_agent.graph import run_workflow_turn
    from financial_analyst_agent.graph.spec_turn import (
        DEFAULT_TASK_MAX_WORKERS,
        TurnContext,
        is_filing_change_proposal,
        is_qualitative_proposal,
        is_structured_proposal,
        run_spec_turn_context,
    )

    finish = timed("conversation_turn", thread_id=thread_id)
    prior = store.load(thread_id) or ThreadState(thread_id=thread_id)
    _check_runtime(prior, runtime)
    workers = DEFAULT_TASK_MAX_WORKERS if max_workers is None else max_workers
    context_token = bind_log_context(thread_id=thread_id, turn=prior.turn_count + 1)
    try:
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
                pending_out = _pending_from_clarify(
                    result, proposed_patch, prior.pending_clarification.question or message
                )
                resumed = True
            else:
                discarded_clarification = True

        guide = None if resumed else guide_reply(
            message, prior.analysis_spec, getattr(runtime.completer, "index", None)
        )
        if guide is not None:
            result = guide
            analysis_spec = None if resets_analysis(message) else prior.analysis_spec
            persist_spec = analysis_spec
        elif not resumed:
            proposal: Any = _complete(runtime.completer, message, prior.analysis_spec)
            proposal = _with_peers(proposal, runtime.ranking)

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
            elif is_structured_proposal(proposal) and (
                not_recorded := not_recorded_reply(
                    message,
                    getattr(runtime.completer, "index", None),
                    getattr(runtime.completer, "outside_index", None),
                )
            ) is not None:
                result = not_recorded
                analysis_spec = prior.analysis_spec
                persist_spec = prior.analysis_spec
            elif is_structured_proposal(proposal):
                result, new_spec, proposed_patch = run_spec_turn_context(
                    TurnContext(
                        message=message,
                        current_spec=prior.analysis_spec,
                        proposal=proposal,
                        on_progress=on_progress,
                        max_workers=workers,
                    ),
                    turn_runtime,
                )
                left_out = unrecorded_companies(
                    message,
                    getattr(runtime.completer, "index", None),
                    getattr(runtime.completer, "outside_index", None),
                )
                if left_out:
                    result = with_banner(result, not_recorded_banner(left_out))
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
            result = with_banner(result, DISCARDED_CLARIFICATION_BANNER)

        result = label_reused_evidence(result, reused=bool(cached_facts.reused_ids))
        if not result.suggestions and guide is None:
            result = result.model_copy(
                update={"suggestions": suggest_follow_ups(result, analysis_spec, runtime.ranking)}
            )

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
            runtime=runtime.kind,
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
        prior_results = store.resolve_results(prior)
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
    finally:
        reset_log_context(context_token)
