"""Streamlit submission and cached-result behavior."""

from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent import app
from financial_analyst_agent.config import AppMode
from financial_analyst_agent.turn import Intent, RendererKind, TurnResult


class _Sidebar:
    def toggle(self, *args: Any, **kwargs: Any) -> bool:
        return True


class _Streamlit:
    def __init__(self) -> None:
        self.sidebar = _Sidebar()
        self.session_state: dict[str, object] = {}
        self._button_values = iter((True, False))

    def set_page_config(self, *args: Any, **kwargs: Any) -> None:
        return None

    def title(self, *args: Any, **kwargs: Any) -> None:
        return None

    def warning(self, *args: Any, **kwargs: Any) -> None:
        return None

    def caption(self, *args: Any, **kwargs: Any) -> None:
        return None

    def text_input(self, *args: Any, **kwargs: Any) -> str:
        return "What was Google's net income?"

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return next(self._button_values)

    def error(self, *args: Any, **kwargs: Any) -> None:
        return None


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

    assert calls == ["What was Google's net income?"]
    assert rendered == [result, result]
