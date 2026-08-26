"""One Streamlit window: multi-turn thread, tool cards, answers."""

from __future__ import annotations

import html
import re
from pathlib import Path

import streamlit as st
import streamlit_shadcn_ui as ui  # type: ignore[import-untyped]

from financial_analyst_agent.config import AppMode, get_settings
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.presentation import (
    DisplayTable,
    Presentation,
    QuarterlyFactCard,
    format_field_name,
    metric_groups,
    present_turn,
)
from financial_analyst_agent.runtime import runtime_for_kill_switch
from financial_analyst_agent.thread_store import LocalThreadStore, ThreadState
from financial_analyst_agent.turn import TurnResult

_GOLD_QUERY = "What was Google's net income based on their latest quarterly report?"
_MD_LINK = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)$")
_DEFAULT_THREAD_ID = "local"
_CAPABILITIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Look up quarterly 10-Q financial facts or market cap for any "
        "operating publicly-listed US company",
        (
            "What was Microsoft's latest quarterly revenue?",
            "What is Apple's market cap?",
        ),
    ),
    (
        "Compare companies on metrics, rank by market cap, or combine rank and lookup",
        (
            "Compare Eli Lilly and Merck net margins",
            "What are the top 10 tech companies and R&D spend for each?",
        ),
    ),
    (
        "Access and analyze relevant financial news linked to specific companies",
        ("What's going on with Eli Lilly's obesity drugs?",),
    ),
    (
        "Answer general queries and provide qualitative industry analysis",
        ("How could AI change bank underwriting?",),
    ),
)
KILL_SWITCH_BANNER = (
    "KILL-SWITCH ON — fixture runtime (recorded facts, not live EDGAR). "
    "Say this out loud. Do not present a cassette as live."
)


def thread_store_root() -> Path:
    """Durable local root for conversation threads (no database server)."""
    return Path(".cache") / "threads"


def render_turn_result(result: TurnResult, *, turn_index: int = 0) -> None:
    _render_presentation(present_turn(result), turn_index=turn_index)


def _render_presentation(presented: Presentation, *, turn_index: int = 0) -> None:
    st.badge(presented.intent, color="blue")
    for banner in presented.banners:
        st.info(banner)
    for hit in presented.citations:
        published = f" ({hit.published})" if hit.published else ""
        st.markdown(f"[{hit.index}] [{hit.title}]({hit.url}){published}")
    if presented.fact_card is not None:
        _render_fact_card(presented.fact_card, turn_index=turn_index)
    if presented.table is not None:
        _render_table(presented.table)
    if presented.candidates:
        st.info("Ambiguous metric. Retype one of these names.")
        for name in presented.candidates:
            st.markdown(f"- {name}")
    elif presented.message is not None:
        st.error(presented.message)
    if presented.essay is not None:
        st.markdown(presented.essay)
    for trace in presented.traces:
        with st.expander(trace.header, expanded=False):
            groups = [
                (title, fields)
                for title, fields in (
                    ("Query", trace.inputs),
                    ("Result Provenance", trace.outputs),
                )
                if fields
            ]
            if len(groups) == 2:
                columns = st.columns(2)
                for column, (title, fields) in zip(columns, groups, strict=True):
                    with column:
                        _render_trace_group(title, fields)
            else:
                for title, fields in groups:
                    _render_trace_group(title, fields)


def _trace_label_width(labels: tuple[str, ...]) -> int:
    longest = max(len(label) for label in labels)
    return min(180, max(72, longest * 9 + 24))


def _render_trace_group(title: str, fields: tuple[tuple[str, str], ...]) -> None:
    st.caption(title)
    labeled = tuple(label for label, value in fields if value and "\n" not in value)
    label_width = _trace_label_width(labeled) if labeled else 72
    rows: list[tuple[str, str]] = []

    def flush_rows() -> None:
        if rows:
            st.html(_trace_rows_html(rows, label_width))
            rows.clear()

    for label, value in fields:
        if "\n" in value:
            flush_rows()
            if label:
                st.markdown(f"**{label}**")
            st.markdown(value)
            continue
        if not value:
            flush_rows()
            if not label:
                st.space("medium")
            continue
        rows.append((label, value))
    flush_rows()


def _html_trace_value(value: str) -> str:
    match = _MD_LINK.fullmatch(value)
    if match is None:
        return html.escape(value)
    text, url = match.groups()
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(text)}</a>'


def _trace_rows_html(items: list[tuple[str, str]], label_width: int) -> str:
    cells = "".join(
        "<div>"
        f"<strong>{html.escape(label)}</strong>"
        "</div>"
        f"<div>{_html_trace_value(value)}</div>"
        for label, value in items
    )
    return (
        '<div style="display:grid;'
        f"grid-template-columns:{label_width}px 1fr;"
        'column-gap:0.5rem;row-gap:0.15rem;align-items:center">'
        f"{cells}</div>"
    )


def _render_fact_card(card: QuarterlyFactCard, *, turn_index: int = 0) -> None:
    ui.metric_card(
        label=card.metric_header,
        value=card.amount,
        description=f"{card.company_name} · {card.ticker}",
        key=f"lookup-fact-{turn_index}",
    )
    st.caption(card.period_label)
    filing = f"[Filing]({card.source_url})" if card.source_url else ""
    st.markdown(f"`{card.form}` · `{card.accession_number}` · `{card.concept}` · {filing}")


def _value_column_format(table: DisplayTable) -> str:
    if "value" not in table.keys:
        return "compact"
    index = table.keys.index("value")
    for row in table.rows:
        text = row[index]
        if text.endswith("%"):
            return "percent"
        if text.endswith("x"):
            return "%.1fx"
        if text.startswith("$") or text.startswith("-$"):
            return "compact"
    return "compact"


def _render_table(table: DisplayTable) -> None:
    records = []
    for row_index, row in enumerate(table.rows):
        record: dict[str, object] = {}
        for col_index, header in enumerate(table.headers):
            if table.numbers and table.keys[col_index] in {"rank", "value"}:
                record[header] = table.numbers[row_index][col_index]
            else:
                record[header] = row[col_index]
        records.append(record)

    column_config = {}
    source_header = format_field_name("source_url")
    if source_header in table.headers:
        column_config[source_header] = st.column_config.LinkColumn(display_text="Filing")
    if table.numbers:
        for col_index, header in enumerate(table.headers):
            if all(row[col_index] is None for row in table.numbers):
                continue
            key = table.keys[col_index]
            if key == "rank":
                column_config[header] = st.column_config.NumberColumn(format="%d")
            elif key == "value":
                column_config[header] = st.column_config.NumberColumn(
                    format=_value_column_format(table)
                )
    if column_config:
        st.dataframe(records, width="stretch", column_config=column_config)
    else:
        st.dataframe(records, width="stretch")


def _render_capabilities() -> None:
    with st.expander("What you can ask", expanded=False):
        blocks: list[str] = []
        for description, examples in _CAPABILITIES:
            example_lines = "\n".join(f"- {example}" for example in examples)
            blocks.append(f"{description}\n\n{example_lines}")
        st.markdown("\n\n".join(blocks))


def _render_metric_catalog() -> None:
    with st.expander("Supported metrics", expanded=False):
        columns = st.columns(len(metric_groups()))
        for column, (title, names) in zip(columns, metric_groups(), strict=True):
            with column:
                st.caption(title)
                st.markdown("  \n".join(f":gray[{name}]" for name in names))


def _history_pairs(state: ThreadState) -> list[tuple[str, TurnResult]]:
    pairs: list[tuple[str, TurnResult]] = []
    for message, result in zip(state.messages, state.results, strict=False):
        pairs.append((message.content, result))
    return pairs


def _ensure_thread_and_history(store: LocalThreadStore, kill_switch: bool) -> None:
    if "thread_id" not in st.session_state:
        st.session_state["thread_id"] = _DEFAULT_THREAD_ID
    if "history" in st.session_state:
        return
    state = store.load(st.session_state["thread_id"])
    if state is None or not state.results:
        st.session_state["history"] = []
        return
    st.session_state["history"] = _history_pairs(state)
    st.session_state["history_kill_switch"] = kill_switch


def _render_history() -> None:
    history: list[tuple[str, TurnResult]] = list(st.session_state.get("history") or [])
    for index, (message, result) in enumerate(history):
        st.markdown(f"**You:** {message}")
        render_turn_result(result, turn_index=index)


def main() -> None:
    st.set_page_config(
        page_title="Financial analyst agent",
        page_icon=":material/query_stats:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    settings = get_settings()
    kill_switch = st.sidebar.toggle(
        "Fixture kill-switch",
        value=settings.app_mode is AppMode.FIXTURE,
        help="Recorded adapters. Announce this if you use it.",
    )
    with st.container(horizontal=True, vertical_alignment="center"):
        st.title("Financial analyst agent")
        ui.badge(
            "Fixture" if kill_switch else "Live",
            variant="destructive" if kill_switch else "default",
            key="runtime-status",
        )
    if kill_switch:
        st.warning(KILL_SWITCH_BANNER)
    else:
        st.caption("Live runtime — SEC XBRL, OpenAI planner, Tavily news.")

    store = LocalThreadStore(thread_store_root())
    _ensure_thread_and_history(store, kill_switch)

    if (
        st.session_state.get("history")
        and st.session_state.get("history_kill_switch") != kill_switch
    ):
        st.session_state["history"] = []
        st.session_state.pop("history_kill_switch", None)

    with st.form("ask"):
        query = st.text_input("Ask a question", value=_GOLD_QUERY)
        submitted = st.form_submit_button("Ask", type="primary")
    _render_capabilities()
    _render_metric_catalog()

    if submitted:
        if st.session_state.get("turn_in_flight"):
            st.info("A turn is already running.")
        else:
            st.session_state["turn_in_flight"] = True
            try:
                with st.spinner("Running turn…"):
                    turn = run_conversation_turn(
                        st.session_state["thread_id"],
                        query,
                        runtime_for_kill_switch(enabled=kill_switch),
                        store=store,
                    )
            except ConfigurationError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Turn failed: {exc}")
            else:
                st.session_state["history"] = _history_pairs(
                    ThreadState(
                        thread_id=turn.thread_id,
                        messages=turn.messages,
                        results=turn.results,
                        last_result=turn.last_result,
                    )
                )
                st.session_state["history_kill_switch"] = kill_switch
            finally:
                st.session_state["turn_in_flight"] = False

    _render_history()


if __name__ == "__main__":
    main()
