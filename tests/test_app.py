"""Streamlit submission and cached-result behavior."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent import app
from financial_analyst_agent.config import AppMode
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.presentation import DisplayTable
from financial_analyst_agent.turn import Intent, NewsHit, RendererKind, ToolTrace, TurnResult


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
        self.infos: list[str] = []
        self.dataframes: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.link_columns: list[tuple[tuple[Any, ...], dict[str, Any], object]] = []
        self.column_config = SimpleNamespace(LinkColumn=self._link_column)
        self.markdowns: list[str] = []
        self.column_specs: list[tuple[Any, dict[str, Any]]] = []
        self.containers: list[dict[str, Any]] = []
        self.spaces: list[object] = []

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

    def columns(self, spec: Any, **kwargs: Any) -> list[Any]:
        self.column_specs.append((spec, kwargs))
        count = spec if isinstance(spec, int) else len(spec)
        return [self for _ in range(count)]

    @contextmanager
    def container(self, *args: Any, **kwargs: Any):
        self.containers.append(kwargs)
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
    assert fake_streamlit.infos == ["Ambiguous metric. Retype one of these names."]
    assert "- Gross profit" in fake_streamlit.markdowns
    assert "- Operating income" in fake_streamlit.markdowns
    assert "- Net income" in fake_streamlit.markdowns


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


def test_render_lookup_trace_uses_query_and_result_provenance_captions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args={"company": "Google", "metric": "net_income"},
                provenance={
                    "form": "10-Q",
                    "accession_number": "0001652044-26-000048",
                    "taxonomy": "us-gaap",
                    "concept": "NetIncomeLoss",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm",
                    "start_date": "2026-01-01",
                    "end_date": "2026-03-31",
                    "source": "sec_xbrl",
                },
            )
        ],
        table_rows=[],
    )

    app.render_turn_result(result)

    assert "Query" in fake_streamlit.markdowns
    assert "Result Provenance" in fake_streamlit.markdowns
    assert "Results Provenance" not in fake_streamlit.markdowns
    assert "Query fields" not in fake_streamlit.markdowns
    assert "Inputs" not in fake_streamlit.markdowns
    assert "Outputs" not in fake_streamlit.markdowns
    assert "**Company:** Google" not in fake_streamlit.markdowns
    assert "**Company**" in fake_streamlit.markdowns
    assert "Google" in fake_streamlit.markdowns
    assert "**Metric**" in fake_streamlit.markdowns
    assert "**Accession number**" in fake_streamlit.markdowns
    assert "0001652044-26-000048" in fake_streamlit.markdowns
    assert "`0001652044-26-000048`" not in fake_streamlit.markdowns
    assert "**Start date**" in fake_streamlit.markdowns
    assert "**End date**" in fake_streamlit.markdowns
    assert not any("Period:" in item for item in fake_streamlit.markdowns)
    assert "**Form**" in fake_streamlit.markdowns
    assert "10-Q" in fake_streamlit.markdowns
    assert "**Taxonomy**" in fake_streamlit.markdowns
    assert "us-gaap" in fake_streamlit.markdowns
    assert "**Source**" in fake_streamlit.markdowns
    assert "SEC EDGAR" in fake_streamlit.markdowns
    assert "sec_xbrl" not in fake_streamlit.markdowns
    assert "**Source URL**" in fake_streamlit.markdowns
    assert any(
        "[www.sec.gov/…/goog-20260331.htm](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm)"
        in item
        for item in fake_streamlit.markdowns
    )
    assert not any("[Filing](" in item for item in fake_streamlit.markdowns)


def test_render_trace_fields_keep_compact_label_value_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_streamlit = _Streamlit()
    monkeypatch.setattr(app, "st", fake_streamlit)
    monkeypatch.setattr(
        app,
        "ui",
        SimpleNamespace(badge=lambda *a, **k: None, metric_card=lambda *a, **k: None),
    )
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args={"company": "Google", "metric": "net_income"},
                provenance={
                    "form": "10-Q",
                    "accession_number": "0001652044-26-000048",
                    "taxonomy": "us-gaap",
                    "concept": "NetIncomeLoss",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm",
                    "start_date": "2026-01-01",
                    "end_date": "2026-03-31",
                    "source": "sec_xbrl",
                },
            )
        ],
        table_rows=[],
    )

    app.render_turn_result(result)

    assert (0.38, 0.62) not in [spec for spec, _kwargs in fake_streamlit.column_specs]
    compact_rows = [
        kwargs
        for kwargs in fake_streamlit.containers
        if kwargs.get("horizontal") is True and kwargs.get("gap") == "xsmall"
    ]
    assert compact_rows
    tight_stacks = [
        kwargs
        for kwargs in fake_streamlit.containers
        if not kwargs.get("horizontal") and kwargs.get("gap") == "xxsmall"
    ]
    assert tight_stacks
    label_widths = [
        kwargs["width"]
        for kwargs in fake_streamlit.containers
        if isinstance(kwargs.get("width"), int)
    ]
    assert label_widths
    assert all(72 <= width <= 180 for width in label_widths)


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

    assert "Result Provenance" in fake_streamlit.markdowns
    assert "**Net income**" in fake_streamlit.markdowns
    assert "$100.00 M" in fake_streamlit.markdowns
    assert "**Net income — $100.00 M**" not in fake_streamlit.markdowns
    assert "**Components**" not in fake_streamlit.markdowns
    assert "**CIK**" not in fake_streamlit.markdowns
    assert fake_streamlit.markdowns.index("**Net income**") < fake_streamlit.markdowns.index(
        "**Concept**"
    )
    concept_at = fake_streamlit.markdowns.index("**Concept**")
    form_at = fake_streamlit.markdowns.index("**Form**")
    assert concept_at < form_at
    assert "**Form**" in fake_streamlit.markdowns
    assert "**Accession number**" in fake_streamlit.markdowns
    assert "**Taxonomy**" in fake_streamlit.markdowns
    assert "**Concept**" in fake_streamlit.markdowns
    assert "**Start date**" in fake_streamlit.markdowns
    assert "**End date**" in fake_streamlit.markdowns
    assert "**Source**" in fake_streamlit.markdowns
    assert "SEC EDGAR" in fake_streamlit.markdowns
    assert "**Source URL**" in fake_streamlit.markdowns
    assert "`0001594805`" not in fake_streamlit.markdowns
    assert "`NetIncomeLoss`" not in fake_streamlit.markdowns
    assert not any("[Filing](" in item for item in fake_streamlit.markdowns)
    assert any("[www.sec.gov/…/shop.htm](" in item for item in fake_streamlit.markdowns)
    assert "**Revenue**" in fake_streamlit.markdowns
    assert "$1.00 B" in fake_streamlit.markdowns
    assert "medium" in fake_streamlit.spaces
    tight_stacks = [
        kwargs
        for kwargs in fake_streamlit.containers
        if not kwargs.get("horizontal") and kwargs.get("gap") == "xxsmall"
    ]
    assert len(tight_stacks) >= 2


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
