"""Streamlit submission and multi-turn audience-window behavior."""

import re
from collections.abc import Iterable
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent import app
from financial_analyst_agent.config import AppMode
from financial_analyst_agent.conversation import ConversationTurn
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.presentation import DisplayTable
from financial_analyst_agent.thread_store import LocalThreadStore, ThreadMessage, ThreadState
from financial_analyst_agent.turn import (
    Intent,
    NewsHit,
    RendererKind,
    TableRow,
    ToolTrace,
    TurnResult,
)


class _Sidebar:
    def __init__(self, values: tuple[bool, ...]) -> None:
        self._values = iter(values)

    def toggle(self, *args: Any, **kwargs: Any) -> bool:
        return next(self._values)


class _Streamlit:
    def __init__(
        self,
        *,
        chat_values: tuple[str | None, ...] = ("What was Google's net income?", None),
        start_over_values: tuple[bool, ...] = (),
        kill_switch_values: tuple[bool, ...] = (True, True),
    ) -> None:
        self.sidebar = _Sidebar(kill_switch_values)
        self.session_state: dict[str, object] = {}
        self._chat_values = iter(chat_values)
        self._start_over_values = iter(start_over_values)
        self.page_config: dict[str, Any] = {}
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.dataframes: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.link_columns: list[tuple[tuple[Any, ...], dict[str, Any], object]] = []
        self.number_columns: list[tuple[tuple[Any, ...], dict[str, Any], object]] = []
        self.column_config = SimpleNamespace(
            LinkColumn=self._link_column,
            NumberColumn=self._number_column,
        )
        self.markdowns: list[str] = []
        self.column_specs: list[tuple[Any, dict[str, Any]]] = []
        self.containers: list[dict[str, Any]] = []
        self.expanders: list[tuple[str, bool]] = []
        self.spaces: list[object] = []
        self.htmls: list[str] = []
        self.chat_inputs: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.chat_messages: list[str] = []
        self.buttons: list[str] = []
        self.forms: list[object] = []
        self.reruns = 0
        self.bottom = self
        self.selectboxes: list[tuple[str, list[str]]] = []
        self.charts: list[str] = []
        self.link_buttons: list[tuple[str, str]] = []
        self.button_disabled: list[tuple[str, bool]] = []
        self.pills: list[object] = []
        self.warnings: list[str] = []

    def __enter__(self) -> "_Streamlit":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def set_page_config(self, *args: Any, **kwargs: Any) -> None:
        self.page_config = kwargs

    def title(self, *args: Any, **kwargs: Any) -> None:
        return None

    def warning(self, *args: Any, **kwargs: Any) -> None:
        if args:
            self.warnings.append(str(args[0]))

    def caption(self, *args: Any, **kwargs: Any) -> None:
        if args:
            self.markdowns.append(str(args[0]))

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        if args:
            self.markdowns.append(str(args[0]))

    def html(self, *args: Any, **kwargs: Any) -> None:
        if args:
            self.htmls.append(str(args[0]))

    def space(self, *args: Any, **kwargs: Any) -> None:
        size = args[0] if args else kwargs.get("size", "small")
        self.spaces.append(size)

    def badge(self, *args: Any, **kwargs: Any) -> None:
        return None

    def error(self, *args: Any, **kwargs: Any) -> None:
        self.errors.append(str(args[0]))

    def info(self, *args: Any, **kwargs: Any) -> None:
        if args:
            self.infos.append(str(args[0]))

    def dataframe(self, *args: Any, **kwargs: Any) -> None:
        self.dataframes.append((args, kwargs))

    def _link_column(self, *args: Any, **kwargs: Any) -> object:
        marker = object()
        self.link_columns.append((args, kwargs, marker))
        return marker

    def _number_column(self, *args: Any, **kwargs: Any) -> object:
        marker = object()
        self.number_columns.append((args, kwargs, marker))
        return marker

    @contextmanager
    def form(self, *args: Any, **kwargs: Any):
        self.forms.append(args[0] if args else kwargs.get("key"))
        yield None

    def text_input(self, *args: Any, **kwargs: Any) -> str:
        raise AssertionError("Ask must use st.chat_input, not st.text_input")

    def form_submit_button(self, *args: Any, **kwargs: Any) -> bool:
        raise AssertionError("Ask must use st.chat_input, not st.form_submit_button")

    def button(self, *args: Any, **kwargs: Any) -> bool:
        label = str(args[0]) if args else str(kwargs.get("label", ""))
        self.buttons.append(label)
        self.button_disabled.append((label, bool(kwargs.get("disabled", False))))
        if label == "Start over":
            return next(self._start_over_values, False)
        return False

    def link_button(self, label: str, url: str, *args: Any, **kwargs: Any) -> bool:
        self.link_buttons.append((label, url))
        return False

    def selectbox(self, label: str, options: Iterable[Any], *args: Any, **kwargs: Any) -> Any:
        values = list(options)
        format_func = kwargs.get("format_func", str)
        self.selectboxes.append((label, [format_func(value) for value in values]))
        return values[0] if values else ""

    def line_chart(self, *args: Any, **kwargs: Any) -> None:
        self.charts.append("line")

    def bar_chart(self, *args: Any, **kwargs: Any) -> None:
        self.charts.append("bar")

    def pills(self, *args: Any, **kwargs: Any) -> None:
        self.pills.append(args)

    def chat_input(self, *args: Any, **kwargs: Any) -> str | None:
        self.chat_inputs.append((args, kwargs))
        return next(self._chat_values, None)

    @contextmanager
    def chat_message(self, role: str, *args: Any, **kwargs: Any):
        self.chat_messages.append(role)
        yield self

    def rerun(self, *args: Any, **kwargs: Any) -> None:
        self.reruns += 1

    @contextmanager
    def spinner(self, *args: Any, **kwargs: Any):
        yield None

    def progress(self, *args: Any, **kwargs: Any) -> Any:
        bar = SimpleNamespace(updates=[(args, kwargs)])

        def _update(*u_args: Any, **u_kwargs: Any) -> None:
            bar.updates.append((u_args, u_kwargs))

        bar.progress = _update  # type: ignore[attr-defined]
        return bar

    @contextmanager
    def expander(self, *args: Any, **kwargs: Any):
        label = str(args[0]) if args else str(kwargs.get("label", ""))
        expanded = bool(kwargs.get("expanded", False))
        self.expanders.append((label, expanded))
        yield None

    def columns(self, spec: Any, **kwargs: Any) -> list[Any]:
        self.column_specs.append((spec, kwargs))
        count = spec if isinstance(spec, int) else len(spec)
        return [self for _ in range(count)]

    @contextmanager
    def container(self, *args: Any, **kwargs: Any):
        self.containers.append(kwargs)
        yield self


def _patch_main_shell(
    monkeypatch: pytest.MonkeyPatch,
    fake_streamlit: _Streamlit,
    *,
    store_root: Path | None = None,
) -> None:
    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(
            app_mode=AppMode.FIXTURE,
            public_demo=False,
            demo_live_sec=False,
            thread_ttl_seconds=7200,
            max_turns_per_thread=25,
            max_live_sec_requests_per_thread=12,
            snapshot_stale_after_days=30,
        ),
    )
    monkeypatch.setattr(app, "runtime_for_kill_switch", lambda **kwargs: object())
    if store_root is not None:
        monkeypatch.setattr(app, "thread_store_root", lambda: store_root)


def _capture_renders(rendered: list[TurnResult]):
    def capture(result: TurnResult, *, turn_index: int = 0, **_kwargs: Any) -> None:
        rendered.append(result)

    return capture


def test_main_runs_only_on_submit_and_renders_cached_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_streamlit = _Streamlit()
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    calls: list[tuple[str, str]] = []
    rendered: list[TurnResult] = []

    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)

    def fake_conversation_turn(
        thread_id: str,
        message: str,
        runtime: object,
        *,
        store: object,
        **_kwargs: Any,
    ) -> ConversationTurn:
        calls.append((thread_id, message))
        return ConversationTurn(
            thread_id=thread_id,
            result=result,
            messages=(ThreadMessage(role="analyst", content=message),),
            results=(result,),
            last_result=result,
        )

    monkeypatch.setattr(app, "run_conversation_turn", fake_conversation_turn)
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered))

    app.main()
    app.main()

    assert fake_streamlit.page_config.get("initial_sidebar_state") == "collapsed"
    assert len(calls) == 1
    assert calls[0][1] == "What was Google's net income?"
    assert fake_streamlit.session_state["thread_id"] == calls[0][0]
    assert rendered == [result, result]
    catalog = "\n".join(fake_streamlit.markdowns)
    assert fake_streamlit.expanders == [
        ("What you can ask", False),
        ("Supported metrics", False),
    ] * 2
    capabilities = (
        "Look up quarterly 10-Q financial facts or market cap for any "
        "operating publicly-listed US company",
        "Compare companies on metrics, rank by market cap, or combine "
        "rank and lookup",
        "Access and analyze relevant financial news linked to specific companies",
        "Answer general queries and provide qualitative industry analysis",
        "Stay on the same thread to extend the current analysis, or start a new one",
    )
    for sentence in capabilities:
        assert sentence in catalog
        assert f"{sentence}." not in catalog
    examples = (
        "What was Microsoft's latest quarterly revenue?",
        "What is Apple's market cap?",
        "Compare Eli Lilly and Merck net margins",
        "What are the top 10 tech companies and R&D spend for each?",
        "What's going on with Eli Lilly's obesity drugs?",
        "How could AI change bank underwriting?",
        "add Apple",
        "now add operating margin",
        "make that the last four quarters",
        "show year-over-year",
    )
    for example in examples:
        assert example in catalog
        assert f"`{example}`" not in catalog
    assert "Compare Microsoft and Google gross margins" not in catalog
    assert "What are the top 10 companies in technology?" not in catalog
    assert "Reported (SEC EDGAR)" in catalog
    assert "Daily snapshot (FMP)" in catalog
    assert "Calculated" in catalog
    assert "Margins" not in catalog
    assert ":gray[Revenue]" in catalog
    assert ":gray[Gross margin]" in catalog
    assert ":gray[Market cap]" in catalog
    assert "revenue (Revenue)" not in catalog
    assert "cost_of_revenue" not in catalog


def test_main_clears_history_when_runtime_mode_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_streamlit = _Streamlit(kill_switch_values=(True, False))
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    rendered: list[TurnResult] = []

    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(
        app,
        "run_conversation_turn",
        lambda thread_id, message, runtime, *, store, **_kwargs: ConversationTurn(
            thread_id=thread_id,
            result=result,
            messages=(ThreadMessage(role="analyst", content=message),),
            results=(result,),
            last_result=result,
        ),
    )
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered))

    app.main()
    app.main()

    assert rendered == [result]
    assert fake_streamlit.session_state.get("history") in (None, [])


def test_main_keeps_prior_history_when_replacement_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_streamlit = _Streamlit(chat_values=("What was Google's net income?",) * 2)
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    outcomes = iter((result, ConfigurationError("replacement failed")))
    rendered: list[TurnResult] = []

    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)

    def fake_conversation_turn(
        thread_id: str,
        message: str,
        runtime: object,
        *,
        store: object,
        **_kwargs: Any,
    ) -> ConversationTurn:
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return ConversationTurn(
            thread_id=thread_id,
            result=outcome,
            messages=(ThreadMessage(role="analyst", content=message),),
            results=(outcome,),
            last_result=outcome,
        )

    monkeypatch.setattr(app, "run_conversation_turn", fake_conversation_turn)
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered))

    app.main()
    app.main()

    assert rendered == [result, result]
    assert fake_streamlit.errors == ["replacement failed"]


def test_main_keeps_prior_history_on_non_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_streamlit = _Streamlit(chat_values=("What was Google's net income?",))
    previous = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    fake_streamlit.session_state["thread_id"] = "thread-a"
    fake_streamlit.session_state["history"] = [("prior question", previous)]
    fake_streamlit.session_state["history_kill_switch"] = True
    rendered: list[TurnResult] = []

    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(
        app,
        "run_conversation_turn",
        lambda thread_id, message, runtime, *, store, **_kwargs: (
            _ for _ in ()
        ).throw(RuntimeError("provider failed")),
    )
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered))

    app.main()

    assert rendered == [previous]
    assert fake_streamlit.session_state["history"] == [("prior question", previous)]
    assert fake_streamlit.session_state["turn_in_flight"] is False
    assert fake_streamlit.errors == [app.PUBLIC_FAILURE_MESSAGE]


def test_main_persists_quota_reservation_when_turn_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_streamlit = _Streamlit(chat_values=("What was Google's net income?",))
    fake_streamlit.session_state["thread_id"] = "thread-quota"
    store = LocalThreadStore(tmp_path)
    store.save(
        ThreadState(
            thread_id="thread-quota",
            messages=(ThreadMessage(role="analyst", content="prior"),),
            turn_count=3,
            live_sec_requests=4,
        )
    )

    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)

    def fake_turn(
        thread_id: str,
        message: str,
        runtime: object,
        *,
        store: object,
        **_kwargs: Any,
    ) -> ConversationTurn:
        budget = getattr(runtime, "budget", None)
        if budget is None:
            raise AssertionError("runtime must carry the session budget")
        budget.consume_live_sec()
        raise RuntimeError("provider failed")

    monkeypatch.setattr(
        app,
        "runtime_for_kill_switch",
        lambda **kwargs: SimpleNamespace(budget=kwargs.get("budget"), ranking=None),
    )
    monkeypatch.setattr(app, "run_conversation_turn", fake_turn)
    monkeypatch.setattr(app, "render_turn_result", lambda *a, **k: None)

    app.main()

    saved = LocalThreadStore(tmp_path).load("thread-quota")
    assert saved is not None
    assert saved.turn_count == 4
    assert saved.live_sec_requests == 5
    assert saved.messages == (ThreadMessage(role="analyst", content="prior"),)


def test_main_shows_second_turn_without_replacing_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = TurnResult(intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.TABLE)
    second = TurnResult(
        intent=Intent.EXPLAIN,
        tool_traces=[],
        renderer=RendererKind.ESSAY,
        essay="Model analysis.",
        banners=("Model analysis — not grounded in retrieved filings or news.",),
    )
    results = iter((first, second))
    rendered: list[TurnResult] = []
    messages = [
        "What was Google's net income?",
        "How can AI disrupt healthcare?",
    ]
    fake_streamlit = _Streamlit(chat_values=tuple(messages))
    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)

    def fake_conversation_turn(
        thread_id: str,
        message: str,
        runtime: object,
        *,
        store: object,
        **_kwargs: Any,
    ) -> ConversationTurn:
        result = next(results)
        prior = fake_streamlit.session_state.get("history", [])
        all_messages = tuple(
            ThreadMessage(role="analyst", content=item[0]) for item in prior
        ) + (ThreadMessage(role="analyst", content=message),)
        all_results = tuple(item[1] for item in prior) + (result,)
        return ConversationTurn(
            thread_id=thread_id,
            result=result,
            messages=all_messages,
            results=all_results,
            last_result=result,
        )

    monkeypatch.setattr(app, "run_conversation_turn", fake_conversation_turn)
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered))

    app.main()
    app.main()

    assert rendered == [first, first, second]
    assert fake_streamlit.session_state["history"] == [
        (messages[0], first),
        (messages[1], second),
    ]
    assert any(messages[0] in item for item in fake_streamlit.markdowns)
    assert any(messages[1] in item for item in fake_streamlit.markdowns)


def test_main_reloads_thread_history_after_restart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from financial_analyst_agent.evidence_store import retain_result_evidence

    first = TurnResult(intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.TABLE)
    second = TurnResult(
        intent=Intent.EXPLAIN,
        tool_traces=[],
        renderer=RendererKind.ESSAY,
        essay="Model analysis.",
    )
    store = LocalThreadStore(tmp_path)
    first_ref = retain_result_evidence(store.evidence_for("local"), first)
    second_ref = retain_result_evidence(store.evidence_for("local"), second)
    store.save(
        ThreadState(
            thread_id="local",
            messages=(
                ThreadMessage(role="analyst", content="What was Google's net income?"),
                ThreadMessage(role="analyst", content="How can AI disrupt healthcare?"),
            ),
            evidence_refs=(first_ref, second_ref),
            last_result_ref=second_ref,
        )
    )
    fake_streamlit = _Streamlit(chat_values=(None,))
    fake_streamlit.session_state["thread_id"] = "local"
    rendered: list[TurnResult] = []
    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(
        app,
        "run_conversation_turn",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered))

    app.main()

    assert fake_streamlit.session_state["thread_id"] == "local"
    assert rendered == [first, second]
    assert fake_streamlit.session_state["history"] == [
        ("What was Google's net income?", first),
        ("How can AI disrupt healthcare?", second),
    ]


def test_main_clears_in_memory_history_when_thread_expires(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from datetime import UTC, datetime

    from financial_analyst_agent.evidence_store import retain_result_evidence

    previous = TurnResult(intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.TABLE)
    store = LocalThreadStore(tmp_path)
    ref = retain_result_evidence(store.evidence_for("expired"), previous)
    store.save(
        ThreadState(
            thread_id="expired",
            messages=(ThreadMessage(role="analyst", content="prior question"),),
            evidence_refs=(ref,),
            last_result_ref=ref,
            updated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    fake_streamlit = _Streamlit(chat_values=(None,))
    fake_streamlit.session_state["thread_id"] = "expired"
    fake_streamlit.session_state["history"] = [("prior question", previous)]
    fake_streamlit.session_state["history_kill_switch"] = True
    rendered: list[TurnResult] = []
    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(
        app,
        "run_conversation_turn",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered))

    app.main()

    assert fake_streamlit.session_state["history"] == []
    assert fake_streamlit.session_state["thread_id"] != "expired"
    assert rendered == []
    assert store.load("expired") is None


def test_start_over_forgets_persisted_thread_on_reload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from financial_analyst_agent.evidence_store import retain_result_evidence

    first = TurnResult(intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.TABLE)
    store = LocalThreadStore(tmp_path)
    first_ref = retain_result_evidence(store.evidence_for("local"), first)
    store.save(
        ThreadState(
            thread_id="local",
            messages=(
                ThreadMessage(role="analyst", content="What was Google's net income?"),
            ),
            evidence_refs=(first_ref,),
            last_result_ref=first_ref,
        )
    )
    fake_streamlit = _Streamlit(chat_values=(None,), start_over_values=(True,))
    fake_streamlit.session_state["thread_id"] = "local"
    rendered: list[TurnResult] = []
    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(
        app,
        "run_conversation_turn",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")),
    )
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered))

    app.main()

    assert "Start over" in fake_streamlit.buttons
    assert fake_streamlit.session_state.get("history") == []
    assert rendered == []
    assert LocalThreadStore(tmp_path).load("local") is None

    fake_streamlit.chat_messages.clear()
    fake_streamlit = _Streamlit(chat_values=(None,))
    fake_streamlit.session_state.clear()
    rendered_after: list[TurnResult] = []
    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(app, "render_turn_result", _capture_renders(rendered_after))
    app.main()
    assert rendered_after == []
    assert fake_streamlit.session_state.get("history") == []


def test_ask_uses_bottom_chat_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_streamlit = _Streamlit()
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(
        app,
        "run_conversation_turn",
        lambda thread_id, message, runtime, *, store, **_kwargs: ConversationTurn(
            thread_id=thread_id,
            result=result,
            messages=(ThreadMessage(role="analyst", content=message),),
            results=(result,),
            last_result=result,
        ),
    )
    monkeypatch.setattr(app, "render_turn_result", lambda *a, **k: None)

    app.main()

    assert fake_streamlit.forms == []
    assert fake_streamlit.chat_inputs
    placeholder = fake_streamlit.chat_inputs[0][0][0]
    assert placeholder == app._GOLD_QUERY


def test_guided_stories_stay_hidden_while_a_story_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_streamlit = _Streamlit(chat_values=(None,))
    fake_streamlit.session_state["pending_query"] = app.GUIDED_STORIES[3][1]
    result = TurnResult(
        intent=Intent.FILING_CHANGE,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(
        app,
        "run_conversation_turn",
        lambda thread_id, message, runtime, *, store, **_kwargs: ConversationTurn(
            thread_id=thread_id,
            result=result,
            messages=(ThreadMessage(role="analyst", content=message),),
            results=(result,),
            last_result=result,
        ),
    )
    monkeypatch.setattr(app, "render_turn_result", lambda *a, **k: None)

    app.main()

    assert "Verify a quarterly fact" not in fake_streamlit.buttons
    assert "What changed in the 10-Q" not in fake_streamlit.buttons


def test_history_autoscrolls_new_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_streamlit = _Streamlit()
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    _patch_main_shell(monkeypatch, fake_streamlit, store_root=tmp_path)
    monkeypatch.setattr(
        app,
        "run_conversation_turn",
        lambda thread_id, message, runtime, *, store, **_kwargs: ConversationTurn(
            thread_id=thread_id,
            result=result,
            messages=(ThreadMessage(role="analyst", content=message),),
            results=(result,),
            last_result=result,
        ),
    )
    monkeypatch.setattr(app, "render_turn_result", lambda *a, **k: None)

    app.main()

    scrolling = [
        kwargs
        for kwargs in fake_streamlit.containers
        if kwargs.get("autoscroll") is True and kwargs.get("height") == "stretch"
    ]
    assert scrolling
    assert fake_streamlit.chat_messages == ["user", "assistant"]


def test_render_clarify_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_streamlit = _Streamlit()
    monkeypatch.setattr(app, "st", fake_streamlit)
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.CLARIFY,
        candidates=("gross_profit", "operating_income", "net_income"),
    )

    app.render_turn_result(result)

    assert fake_streamlit.errors == []
    assert fake_streamlit.infos == ["Ambiguous metric. Choose one of these names."]
    assert "Gross profit" in fake_streamlit.buttons
    assert "Operating income" in fake_streamlit.buttons
    assert "Net income" in fake_streamlit.buttons


def test_historical_clarification_buttons_are_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    monkeypatch.setattr(app, "st", fake_streamlit)
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.CLARIFY,
        candidates=("gross_profit", "operating_income", "net_income"),
    )

    app.render_turn_result(result, turn_index=0, clarify_enabled=False)

    assert fake_streamlit.button_disabled == [
        ("Gross profit", True),
        ("Operating income", True),
        ("Net income", True),
    ]


def test_render_table_configures_source_url_as_filing_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    source_header = "Source URL"
    table = DisplayTable(
        headers=("Company", source_header),
        keys=("company_name", "source_url"),
        rows=(("Alphabet Inc.", "https://www.sec.gov/example"),),
    )
    monkeypatch.setattr(app, "st", fake_streamlit)

    app._render_table(table)

    assert len(fake_streamlit.link_columns) == 1
    link_args, link_kwargs, marker = fake_streamlit.link_columns[0]
    assert link_args == ()
    assert link_kwargs == {"display_text": "Filing"}
    assert fake_streamlit.dataframes[0][1]["column_config"] == {source_header: marker}


def test_render_table_passes_metric_values_as_numbers_for_sorting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    _patch_render_streamlit(monkeypatch, fake_streamlit)
    app.render_turn_result(
        TurnResult(
            intent=Intent.RANK_AND_LOOKUP,
            renderer=RendererKind.TABLE,
            tool_traces=[],
            table_rows=[
                TableRow(
                    company_name="Microsoft Corporation",
                    ticker="MSFT",
                    cik="0000789019",
                    metric="research_and_development",
                    rank=3,
                    value=Decimal("8920000000"),
                    currency="USD",
                ),
                TableRow(
                    company_name="Apple Inc.",
                    ticker="AAPL",
                    cik="0000320193",
                    metric="research_and_development",
                    rank=2,
                    value=Decimal("11730000000"),
                    currency="USD",
                ),
                TableRow(
                    company_name="Advanced Micro Devices, Inc.",
                    ticker="AMD",
                    cik="0000002488",
                    metric="research_and_development",
                    rank=8,
                    value=Decimal("2530000000"),
                    currency="USD",
                ),
            ],
        )
    )

    records = fake_streamlit.dataframes[0][0][0]
    values = [row["Value"] for row in records]
    assert all(isinstance(value, (int, float)) for value in values)
    assert sorted(values, reverse=True) == [
        11_730_000_000.0,
        8_920_000_000.0,
        2_530_000_000.0,
    ]


_GOOGLE_LOOKUP_PROVENANCE = {
    "form": "10-Q",
    "accession_number": "0001652044-26-000048",
    "taxonomy": "us-gaap",
    "concept": "NetIncomeLoss",
    "source_url": (
        "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm"
    ),
    "start_date": "2026-01-01",
    "end_date": "2026-03-31",
    "source": "sec_xbrl",
}


def _google_lookup_trace_result() -> TurnResult:
    return TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args={"company": "Google", "metric": "net_income"},
                provenance=_GOOGLE_LOOKUP_PROVENANCE,
            )
        ],
        table_rows=[],
    )


def _patch_render_streamlit(monkeypatch: pytest.MonkeyPatch, fake_streamlit: _Streamlit) -> None:
    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )


def _trace_output(fake_streamlit: _Streamlit) -> str:
    return "\n".join([*fake_streamlit.markdowns, *fake_streamlit.htmls])


def test_render_lookup_trace_uses_query_and_result_provenance_captions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    _patch_render_streamlit(monkeypatch, fake_streamlit)

    app.render_turn_result(_google_lookup_trace_result())
    output = _trace_output(fake_streamlit)

    assert "Query" in fake_streamlit.markdowns
    assert "Result Provenance" in fake_streamlit.markdowns
    assert "Results Provenance" not in output
    assert "Query fields" not in output
    assert "Inputs" not in output
    assert "Outputs" not in output
    assert "**Company:** Google" not in output
    assert "<strong>Company</strong>" in output
    assert "Google" in output
    assert "<strong>Metric</strong>" in output
    assert "<strong>Accession number</strong>" in output
    assert "0001652044-26-000048" in output
    assert "`0001652044-26-000048`" not in output
    assert "<strong>Start date</strong>" in output
    assert "<strong>End date</strong>" in output
    assert "Period:" not in output
    assert "<strong>Form</strong>" in output
    assert "10-Q" in output
    assert "<strong>Taxonomy</strong>" in output
    assert "us-gaap" in output
    assert "<strong>Source</strong>" in output
    assert "SEC EDGAR" in output
    assert "sec_xbrl" not in output
    assert "<strong>Source URL</strong>" in output
    assert (
        '<a href="https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm">'
        "www.sec.gov/…/goog-20260331.htm</a>"
    ) in output
    assert "[Filing](" not in output


def test_render_trace_fields_keep_compact_label_value_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    _patch_render_streamlit(monkeypatch, fake_streamlit)

    app.render_turn_result(_google_lookup_trace_result())

    assert (0.38, 0.62) not in [spec for spec, _kwargs in fake_streamlit.column_specs]
    assert not any(
        kwargs.get("horizontal") is True and kwargs.get("gap") == "xsmall"
        for kwargs in fake_streamlit.containers
    )
    grids = [item for item in fake_streamlit.htmls if "grid-template-columns:" in item]
    assert grids
    widths = [
        int(match.group(1))
        for item in grids
        for match in [re.search(r"grid-template-columns:(\d+)px", item)]
        if match
    ]
    assert widths
    assert all(72 <= width <= 180 for width in widths)


def test_render_formula_trace_uses_lookup_provenance_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    monkeypatch.setattr(app, "st", fake_streamlit)
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={"issuers": ["Shopify"], "metric": "net_margin"},
                provenance={
                    "components": [
                        {
                            "cik": "0001594805",
                            "metric": "net_income",
                            "value": "100000000",
                            "form": "10-Q",
                            "taxonomy": "us-gaap",
                            "source": "sec_xbrl",
                            "accession_number": "0001594805-26-000047",
                            "concept": "NetIncomeLoss",
                            "start_date": "2026-04-01",
                            "end_date": "2026-06-30",
                            "source_url": "https://www.sec.gov/Archives/edgar/data/1594805/shop.htm",
                        },
                        {
                            "cik": "0001594805",
                            "metric": "revenue",
                            "value": "1000000000",
                            "form": "10-Q",
                            "taxonomy": "us-gaap",
                            "source": "sec_xbrl",
                            "accession_number": "0001594805-26-000047",
                            "concept": "Revenues",
                            "start_date": "2026-04-01",
                            "end_date": "2026-06-30",
                            "source_url": "https://www.sec.gov/Archives/edgar/data/1594805/shop.htm",
                        },
                    ]
                },
            )
        ],
    )

    app.render_turn_result(result)
    output = _trace_output(fake_streamlit)

    assert "Result Provenance" in fake_streamlit.markdowns
    assert "<strong>Net income</strong>" in output
    assert "$100.00 M" in output
    assert "**Net income — $100.00 M**" not in output
    assert "**Components**" not in output
    assert "<strong>CIK</strong>" not in output
    assert output.index("<strong>Net income</strong>") < output.index("<strong>Concept</strong>")
    assert output.index("<strong>Concept</strong>") < output.index("<strong>Form</strong>")
    assert "<strong>Form</strong>" in output
    assert "<strong>Accession number</strong>" in output
    assert "<strong>Taxonomy</strong>" in output
    assert "<strong>Concept</strong>" in output
    assert "<strong>Start date</strong>" in output
    assert "<strong>End date</strong>" in output
    assert "<strong>Source</strong>" in output
    assert "SEC EDGAR" in output
    assert "<strong>Source URL</strong>" in output
    assert "`0001594805`" not in output
    assert "`NetIncomeLoss`" not in output
    assert "[Filing](" not in output
    assert (
        '<a href="https://www.sec.gov/Archives/edgar/data/1594805/shop.htm">'
        "www.sec.gov/…/shop.htm</a>"
    ) in output
    assert "<strong>Revenue</strong>" in output
    assert "$1.00 B" in output
    assert "medium" in fake_streamlit.spaces
    grids = [item for item in fake_streamlit.htmls if "grid-template-columns:" in item]
    assert len(grids) >= 2


def test_render_news_citations_are_numbered(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_streamlit = _Streamlit()
    monkeypatch.setattr(app, "st", fake_streamlit)
    result = TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="Packaging remains tight [1].",
        citations=[
            NewsHit(title="First hit", url="https://example.com/first", published="Jan 1, 2026"),
            NewsHit(title="Second hit", url="https://example.com/second"),
        ],
        tool_traces=[],
    )

    app.render_turn_result(result)

    assert "[1] [First hit](https://example.com/first) (Jan 1, 2026)" in fake_streamlit.markdowns
    assert "[2] [Second hit](https://example.com/second)" in fake_streamlit.markdowns
    assert not any(item.startswith("- [") for item in fake_streamlit.markdowns)
