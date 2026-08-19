"""Streamlit submission and cached-result behavior."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent import app
from financial_analyst_agent.config import AppMode
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.presentation import DisplayTable
from financial_analyst_agent.turn import Intent, RendererKind, TurnResult


class _Sidebar:
    def __init__(self, values: tuple[bool, ...]) -> None:
        self._values = iter(values)

    def toggle(self, *args: Any, **kwargs: Any) -> bool:
        return next(self._values)


class _Streamlit:
    def __init__(
        self,
        *,
        button_values: tuple[bool, ...] = (True, False),
        kill_switch_values: tuple[bool, ...] = (True, True),
    ) -> None:
        self.sidebar = _Sidebar(kill_switch_values)
        self.session_state: dict[str, object] = {}
        self._button_values = iter(button_values)
        self.page_config: dict[str, Any] = {}
        self.errors: list[str] = []
        self.dataframes: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.link_columns: list[tuple[tuple[Any, ...], dict[str, Any], object]] = []
        self.column_config = SimpleNamespace(LinkColumn=self._link_column)
        self.markdowns: list[str] = []

    def __enter__(self) -> "_Streamlit":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def set_page_config(self, *args: Any, **kwargs: Any) -> None:
        self.page_config = kwargs

    def title(self, *args: Any, **kwargs: Any) -> None:
        return None

    def warning(self, *args: Any, **kwargs: Any) -> None:
        return None

    def caption(self, *args: Any, **kwargs: Any) -> None:
        if args:
            self.markdowns.append(str(args[0]))

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        if args:
            self.markdowns.append(str(args[0]))

    def space(self, *args: Any, **kwargs: Any) -> None:
        return None

    def badge(self, *args: Any, **kwargs: Any) -> None:
        return None

    def error(self, *args: Any, **kwargs: Any) -> None:
        self.errors.append(str(args[0]))

    def info(self, *args: Any, **kwargs: Any) -> None:
        return None

    def dataframe(self, *args: Any, **kwargs: Any) -> None:
        self.dataframes.append((args, kwargs))

    def _link_column(self, *args: Any, **kwargs: Any) -> object:
        marker = object()
        self.link_columns.append((args, kwargs, marker))
        return marker

    @contextmanager
    def form(self, *args: Any, **kwargs: Any):
        yield None

    def text_input(self, *args: Any, **kwargs: Any) -> str:
        return "What was Google's net income?"

    def form_submit_button(self, *args: Any, **kwargs: Any) -> bool:
        return next(self._button_values)

    def button(self, *args: Any, **kwargs: Any) -> bool:
        raise AssertionError("Ask must use st.form_submit_button, not st.button")

    @contextmanager
    def spinner(self, *args: Any, **kwargs: Any):
        yield None

    @contextmanager
    def expander(self, *args: Any, **kwargs: Any):
        yield None

    def columns(self, spec: Any) -> list[Any]:
        count = spec if isinstance(spec, int) else len(spec)
        return [self for _ in range(count)]

    @contextmanager
    def container(self, *args: Any, **kwargs: Any):
        yield self


def test_main_runs_only_on_submit_and_renders_cached_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    calls: list[str] = []
    rendered: list[TurnResult] = []

    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(app_mode=AppMode.FIXTURE),
    )
    monkeypatch.setattr(app, "runtime_for_kill_switch", lambda **kwargs: object())

    def fake_run_turn(query: str, runtime: object) -> TurnResult:
        calls.append(query)
        return result

    monkeypatch.setattr(app, "run_turn", fake_run_turn)
    monkeypatch.setattr(app, "render_turn_result", rendered.append)

    app.main()
    app.main()

    assert fake_streamlit.page_config.get("initial_sidebar_state") == "collapsed"
    assert calls == ["What was Google's net income?"]
    assert rendered == [result, result]
    catalog = "\n".join(fake_streamlit.markdowns)
    assert "Supported metrics (SEC EDGAR)" in catalog
    assert "Reported" in catalog
    assert "Margins" in catalog
    assert ":gray[Revenue]" in catalog
    assert ":gray[Gross margin]" in catalog
    assert "revenue (Revenue)" not in catalog
    assert "cost_of_revenue" not in catalog


def test_main_clears_cached_result_when_runtime_mode_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit(kill_switch_values=(True, False))
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    rendered: list[TurnResult] = []

    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(app_mode=AppMode.FIXTURE),
    )
    monkeypatch.setattr(app, "runtime_for_kill_switch", lambda **kwargs: object())
    monkeypatch.setattr(app, "run_turn", lambda query, runtime: result)
    monkeypatch.setattr(app, "render_turn_result", rendered.append)

    app.main()
    app.main()

    assert rendered == [result]
    assert "result" not in fake_streamlit.session_state


def test_main_clears_previous_result_when_replacement_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit(button_values=(True, True))
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    outcomes = iter((result, ConfigurationError("replacement failed")))
    rendered: list[TurnResult] = []

    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(app_mode=AppMode.FIXTURE),
    )
    monkeypatch.setattr(app, "runtime_for_kill_switch", lambda **kwargs: object())

    def fake_run_turn(query: str, runtime: object) -> TurnResult:
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(app, "run_turn", fake_run_turn)
    monkeypatch.setattr(app, "render_turn_result", rendered.append)

    app.main()
    app.main()

    assert rendered == [result]
    assert "result" not in fake_streamlit.session_state
    assert fake_streamlit.errors == ["replacement failed"]


def test_main_cleans_up_non_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit(button_values=(True,))
    previous = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
    )
    fake_streamlit.session_state["result"] = previous
    fake_streamlit.session_state["result_kill_switch"] = True
    rendered: list[TurnResult] = []

    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )
    monkeypatch.setattr(
        app,
        "get_settings",
        lambda: SimpleNamespace(app_mode=AppMode.FIXTURE),
    )
    monkeypatch.setattr(app, "runtime_for_kill_switch", lambda **kwargs: object())
    monkeypatch.setattr(
        app,
        "run_turn",
        lambda query, runtime: (_ for _ in ()).throw(RuntimeError("provider failed")),
    )
    monkeypatch.setattr(app, "render_turn_result", rendered.append)

    app.main()

    assert rendered == []
    assert "result" not in fake_streamlit.session_state
    assert fake_streamlit.session_state["turn_in_flight"] is False
    assert fake_streamlit.errors == ["Turn failed: provider failed"]


def test_render_table_configures_source_url_as_filing_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    source_header = "source_url (Source URL)"
    table = DisplayTable(
        headers=("company_name (Company)", source_header),
        keys=("company_name", "source_url"),
        rows=(("Alphabet Inc.", "https://www.sec.gov/example"),),
    )
    monkeypatch.setattr(app, "st", fake_streamlit)

    app._render_table(table)

    assert len(fake_streamlit.link_columns) == 1
    link_args, link_kwargs, marker = fake_streamlit.link_columns[0]
    assert link_args == ()
    assert link_kwargs == {"display_text": "Filing"}
    assert fake_streamlit.dataframes[0][1]["column_config"] == {
        source_header: marker
    }
