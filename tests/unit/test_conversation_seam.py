"""Conversation seam: thread id + message + runtime → typed conversation turn.

Asserts persistence at the public seam against a real temporary store.
Does not assert checkpointer payloads or LangGraph internals.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY


class _LookupFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        assert company == "Google"
        assert metric == "net_income"
        return SimpleNamespace(
            company_name="Alphabet Inc.",
            ticker="GOOG",
            cik="0001652044",
            metric="net_income",
            value=Decimal("62578000000"),
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            form="10-Q",
            accession_number="0001652044-26-000048",
            taxonomy="us-gaap",
            concept="NetIncomeLoss",
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


class _LookupCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        from financial_analyst_agent.contracts import Intent

        return SimpleNamespace(
            intent=Intent.LOOKUP,
            company="Google",
            metric="net_income",
            issuers=None,
            industry=None,
            limit=None,
            topic=None,
        )


class _ExplainCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        from financial_analyst_agent.contracts import Intent

        return SimpleNamespace(
            intent=Intent.EXPLAIN,
            company=None,
            metric=None,
            issuers=None,
            industry=None,
            limit=None,
            topic="AI disruption in healthcare",
        )


class _NumberFreeEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return FIXTURE_EXPLAIN_ESSAY


def _runtime(
    *, completer: object, facts: object | None = None, essay: object | None = None
) -> object:
    from financial_analyst_agent.contracts import Runtime

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=(facts or _LookupFacts()),  # type: ignore[arg-type]
        essay=essay,  # type: ignore[arg-type]
    )


def test_conversation_seam_returns_typed_turn(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult
    from financial_analyst_agent.conversation import ConversationTurn, run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    message = "What was Google's net income based on their latest quarterly report?"
    turn = run_conversation_turn(
        "thread-a",
        message,
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store,
    )

    assert isinstance(turn, ConversationTurn)
    assert turn.thread_id == "thread-a"
    assert isinstance(turn.result, TurnResult)
    assert turn.result.intent is Intent.LOOKUP
    assert turn.result.renderer is RendererKind.TABLE
    assert turn.result.table_rows[0].ticker == "GOOG"
    assert [m.content for m in turn.messages] == [message]
    assert turn.last_result == turn.result


def test_same_thread_sees_prior_turn_different_thread_starts_clean(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    first = "What was Google's net income based on their latest quarterly report?"
    second = "How can AI disrupt healthcare?"

    turn1 = run_conversation_turn(
        "thread-a",
        first,
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store,
    )
    assert turn1.result.intent is Intent.LOOKUP

    turn2 = run_conversation_turn(
        "thread-a",
        second,
        _runtime(completer=_ExplainCompleter(), essay=_NumberFreeEssay()),  # type: ignore[arg-type]
        store=store,
    )
    assert [m.content for m in turn2.messages] == [first, second]
    assert turn2.result.intent is Intent.EXPLAIN

    other = run_conversation_turn(
        "thread-b",
        second,
        _runtime(completer=_ExplainCompleter(), essay=_NumberFreeEssay()),  # type: ignore[arg-type]
        store=store,
    )
    assert [m.content for m in other.messages] == [second]
    assert other.thread_id == "thread-b"


def test_thread_state_survives_process_restart(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    message = "What was Google's net income based on their latest quarterly report?"
    store1 = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "thread-a",
        message,
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store1,
    )

    # New store instance over the same durable root (new process).
    store2 = LocalThreadStore(tmp_path)
    follow_up = "How can AI disrupt healthcare?"
    turn = run_conversation_turn(
        "thread-a",
        follow_up,
        _runtime(completer=_ExplainCompleter(), essay=_NumberFreeEssay()),  # type: ignore[arg-type]
        store=store2,
    )
    assert [m.content for m in turn.messages] == [message, follow_up]
    assert turn.last_result.intent.value == "explain"


def test_run_state_is_not_persisted_between_turns(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore, ThreadState

    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "thread-a",
        "What was Google's net income based on their latest quarterly report?",
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store,
    )
    state = store.load("thread-a")
    assert isinstance(state, ThreadState)
    dumped = state.model_dump()
    assert set(dumped) == {"thread_id", "messages", "last_result"}
    assert "plan" not in dumped
    assert "runtime" not in dumped
    assert "compiled_tasks" not in dumped


def test_run_turn_is_ephemeral_thread_wrapper() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult
    from financial_analyst_agent.turn import run_turn

    result = run_turn(
        "What was Google's net income based on their latest quarterly report?",
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
    )
    assert isinstance(result, TurnResult)
    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.table_rows[0].value == Decimal("62578000000")
