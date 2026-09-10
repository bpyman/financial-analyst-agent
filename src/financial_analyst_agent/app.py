"""One Streamlit window: multi-turn thread, tool cards, answers."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st
import streamlit_shadcn_ui as ui  # type: ignore[import-untyped]

from financial_analyst_agent.config import AppMode, get_settings
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.domain.errors import ConfigurationError, SessionQuotaError
from financial_analyst_agent.presentation import (
    DisplayTable,
    Presentation,
    QuarterlyFactCard,
    format_field_name,
    metric_groups,
    present_turn,
    spec_chips,
)
from financial_analyst_agent.runtime import runtime_for_kill_switch
from financial_analyst_agent.session import SessionBudget, new_thread_id, snapshot_status
from financial_analyst_agent.thread_store import LocalThreadStore, ThreadState
from financial_analyst_agent.turn import TurnResult

_GOLD_QUERY = "What was Google's net income based on their latest quarterly report?"
_MD_LINK = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)$")
GUIDED_STORIES: tuple[tuple[str, str], ...] = (
    (
        "Verify a quarterly fact",
        "What was Microsoft's latest quarterly pretax income?",
    ),
    (
        "Compare four quarters",
        "What was Microsoft's latest quarterly revenue for the last four quarters?",
    ),
    (
        "Rank then inspect filings",
        "What are the top 10 tech companies and R&D spend for each?",
    ),
    (
        "What changed in the 10-Q",
        "What changed in Microsoft's MD&A and Risk Factors between "
        "0001193125-25-000099 and 0001193125-26-191507?",
    ),
)
PUBLIC_FAILURE_MESSAGE = "The analysis could not be completed. Please try again."
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
    (
        "Stay on the same thread to extend the current analysis, or start a new one",
        (
            "add Apple",
            "now add operating margin",
            "make that the last four quarters",
            "show year-over-year",
        ),
    ),
)
KILL_SWITCH_BANNER = (
    "Guided demo data — recorded SEC facts, not a live EDGAR pull. "
    "Numbers are still produced by the same deterministic renderer."
)
LIVE_RUNTIME_CAPTION = "Live runtime — SEC XBRL, optional planner, cached EDGAR."


def public_error_message(exc: BaseException) -> str:
    if isinstance(exc, (ConfigurationError, SessionQuotaError)):
        return str(exc)
    return PUBLIC_FAILURE_MESSAGE


def thread_store_root() -> Path:
    """Durable local root for conversation threads (no database server)."""
    return Path(".cache") / "threads"


def render_turn_result(result: TurnResult, *, turn_index: int = 0) -> None:
    _render_presentation(present_turn(result), result=result, turn_index=turn_index)


def _render_presentation(
    presented: Presentation,
    *,
    result: TurnResult | None = None,
    turn_index: int = 0,
) -> None:
    st.badge(presented.intent_label or presented.intent, color="blue")
    if presented.chart is not None:
        _render_chart(presented.chart)
    if presented.fact_card is not None:
        _render_fact_card(presented.fact_card, turn_index=turn_index)
    if presented.table is not None:
        _render_table(presented.table)
    if presented.disclosures:
        _render_disclosures(presented.disclosures)
    if presented.evidence:
        _render_evidence_inspector(presented.evidence, turn_index=turn_index)
    for banner in presented.banners:
        st.info(banner)
    for hit in presented.citations:
        published = f" ({hit.published})" if hit.published else ""
        st.markdown(f"[{hit.index}] [{hit.title}]({hit.url}){published}")
    if presented.candidates:
        if tuple(c.casefold() for c in presented.candidates) == ("extend", "replace"):
            st.info("Ambiguous follow-up scope. Choose extend or replace.")
        else:
            st.info("Ambiguous metric. Choose one of these names.")
        slugs = result.candidates if result is not None else presented.candidates
        for slug, label in zip(slugs, presented.candidates, strict=False):
            if st.button(label, key=f"clarify-{turn_index}-{slug}"):
                st.session_state["pending_query"] = slug
                st.rerun()
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
    st.markdown(f"`{card.form}` · `{card.accession_number}` · `{card.concept}`")
    if card.source_url:
        st.link_button("Open filing", card.source_url)


def _render_chart(chart: object) -> None:
    records = list(getattr(chart, "records", ()))
    if not records:
        return
    kind = getattr(chart, "kind", "bar")
    if kind == "line":
        st.line_chart(records, x="Period")
    else:
        st.bar_chart(records, x="Company", y="Value")


def _render_evidence_inspector(items: tuple[object, ...], *, turn_index: int) -> None:
    labels = [
        str(getattr(item, "label", f"Item {index}"))
        for index, item in enumerate(items, start=1)
    ]
    chosen = st.selectbox(
        "Inspect exact source",
        labels,
        key=f"evidence-{turn_index}",
    )
    item = items[labels.index(chosen)]
    st.markdown(f"**{getattr(item, 'amount', '')}**")
    st.caption(f"Exact amount: `{getattr(item, 'raw_amount', '')}`")
    st.markdown(
        f"{getattr(item, 'company_name', '')} · {getattr(item, 'ticker', '')} · "
        f"CIK `{getattr(item, 'cik', '')}`"
    )
    st.markdown(
        f"`{getattr(item, 'form', '')}` · `{getattr(item, 'accession_number', '')}` · "
        f"`{getattr(item, 'concept', '')}`"
    )
    st.caption(getattr(item, "period_label", ""))
    st.caption(getattr(item, "selection_rule", ""))
    url = str(getattr(item, "source_url", "") or "")
    if url:
        st.link_button("Open filing", url)


def _render_disclosures(items: tuple[object, ...]) -> None:
    for index, item in enumerate(items):
        kind = str(getattr(item, "change_kind", "changed")).title()
        heading = f"{getattr(item, 'section_label', 'Section')} · {kind}"
        with st.expander(heading, expanded=index == 0):
            before = str(getattr(item, "before_text", "") or "")
            after = str(getattr(item, "after_text", "") or "")
            if before:
                st.caption("Previous filing")
                st.markdown(before)
            if after:
                st.caption("Current filing")
                st.markdown(after)
            older = str(getattr(item, "older_url", "") or "")
            newer = str(getattr(item, "newer_url", "") or "")
            if older:
                st.link_button("Open previous filing", older, key=f"older-{index}")
            if newer:
                st.link_button("Open current filing", newer, key=f"newer-{index}")


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
    hidden = {"cik", "taxonomy"}
    keep = [index for index, key in enumerate(table.keys) if key not in hidden]
    headers = tuple(table.headers[index] for index in keep)
    keys = tuple(table.keys[index] for index in keep)
    rows = tuple(tuple(row[index] for index in keep) for row in table.rows)
    numbers = (
        tuple(tuple(row[index] for index in keep) for row in table.numbers)
        if table.numbers
        else ()
    )
    table = DisplayTable(headers=headers, keys=keys, rows=rows, numbers=numbers)
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


def _history_pairs(state: ThreadState, store: LocalThreadStore) -> list[tuple[str, TurnResult]]:
    pairs: list[tuple[str, TurnResult]] = []
    results = store.resolve_results(state)
    for message, result in zip(state.messages, results, strict=False):
        pairs.append((message.content, result))
    return pairs


def _ensure_thread_and_history(
    store: LocalThreadStore,
    kill_switch: bool,
    *,
    ttl_seconds: int,
) -> None:
    if "thread_id" not in st.session_state:
        st.session_state["thread_id"] = new_thread_id()
    store.purge_expired(now=datetime.now(UTC), ttl_seconds=ttl_seconds)
    if "history" in st.session_state:
        return
    state = store.load(st.session_state["thread_id"], ttl_seconds=ttl_seconds)
    if state is None or not state.evidence_refs:
        st.session_state["history"] = []
        return
    st.session_state["history"] = _history_pairs(state, store)
    st.session_state["history_kill_switch"] = kill_switch


def _start_over(store: LocalThreadStore) -> None:
    thread_id = str(st.session_state.get("thread_id") or "")
    if thread_id:
        store.clear(thread_id)
    st.session_state["thread_id"] = new_thread_id()
    st.session_state["history"] = []
    st.session_state.pop("history_kill_switch", None)
    st.session_state.pop("turn_in_flight", None)
    st.session_state.pop("pending_query", None)


def _render_history() -> None:
    history: list[tuple[str, TurnResult]] = list(st.session_state.get("history") or [])
    with st.container(height="stretch", autoscroll=True):
        for index, (message, result) in enumerate(history):
            with st.chat_message("user"):
                st.markdown(message)
            with st.chat_message("assistant"):
                render_turn_result(result, turn_index=index)


def _render_guided_stories() -> None:
    columns = st.columns(len(GUIDED_STORIES))
    for column, (label, question) in zip(columns, GUIDED_STORIES, strict=True):
        with column:
            if st.button(label, key=f"story-{label}"):
                st.session_state["pending_query"] = question
                st.rerun()


def _render_spec_chips(store: LocalThreadStore) -> None:
    thread_id = str(st.session_state.get("thread_id") or "")
    if not thread_id:
        return
    state = store.load(thread_id)
    if state is None or state.analysis_spec is None:
        return
    chips = spec_chips(state.analysis_spec)
    if not chips:
        return
    st.caption("Active analysis")
    st.pills("Active analysis", chips, key="spec-chips", disabled=True)


def main() -> None:
    st.set_page_config(
        page_title="Financial analyst agent",
        page_icon=":material/query_stats:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    settings = get_settings()
    public_demo = bool(getattr(settings, "public_demo", False))
    force_fixture = settings.app_mode is AppMode.FIXTURE or (
        public_demo and not settings.demo_live_sec
    )
    kill_switch = st.sidebar.toggle(
        "Recorded demo data",
        value=force_fixture,
        help="Recorded adapters. Numbers still come from the deterministic renderer.",
        disabled=public_demo and not settings.demo_live_sec,
    )
    with st.container(horizontal=True, vertical_alignment="center"):
        st.title("Financial analyst agent")
        ui.badge(
            "Guided demo" if kill_switch else "Live SEC",
            variant="destructive" if kill_switch else "default",
            key="runtime-status",
        )
        start_over = st.button("Start over", icon=":material/refresh:")
    if kill_switch:
        st.warning(KILL_SWITCH_BANNER)
    else:
        st.caption(LIVE_RUNTIME_CAPTION)

    store = LocalThreadStore(thread_store_root())
    if start_over:
        _start_over(store)
        st.rerun()
    _ensure_thread_and_history(store, kill_switch, ttl_seconds=settings.thread_ttl_seconds)

    if (
        st.session_state.get("history")
        and st.session_state.get("history_kill_switch") != kill_switch
    ):
        st.session_state["history"] = []
        st.session_state.pop("history_kill_switch", None)

    ranking_runtime = runtime_for_kill_switch(enabled=kill_switch, settings=settings)
    ranking = getattr(ranking_runtime, "ranking", None)
    if ranking is not None:
        banner, stale = snapshot_status(
            ranking.snapshot_as_of(),
            stale_after_days=settings.snapshot_stale_after_days,
        )
        if stale:
            st.warning(banner)
        else:
            st.caption(banner)

    if not st.session_state.get("history"):
        _render_guided_stories()
    _render_spec_chips(store)
    _render_capabilities()
    _render_metric_catalog()

    pending = str(st.session_state.pop("pending_query", "") or "")
    with st.bottom:
        typed = st.chat_input(_GOLD_QUERY, submit_mode="disable")
    query = pending or (typed.strip() if typed else "")
    if query:
        if st.session_state.get("turn_in_flight"):
            st.info("A turn is already running.")
        else:
            st.session_state["turn_in_flight"] = True
            try:
                thread_id = str(st.session_state["thread_id"])
                prior = store.load(thread_id, ttl_seconds=settings.thread_ttl_seconds)
                budget = SessionBudget.from_counts(
                    turns=prior.turn_count if prior is not None else 0,
                    live_sec_requests=prior.live_sec_requests if prior is not None else 0,
                    max_turns=settings.max_turns_per_thread,
                    max_live_sec_requests=settings.max_live_sec_requests_per_thread,
                )
                budget.consume_turn()
                progress = st.progress(0, text="Running analysis…")

                def _on_progress(done: int, total: int) -> None:
                    fraction = 0.0 if total <= 0 else done / total
                    progress.progress(
                        fraction,
                        text=f"Completed {done} of {total} cells…",
                    )

                turn = run_conversation_turn(
                    thread_id,
                    query,
                    runtime_for_kill_switch(
                        enabled=kill_switch,
                        settings=settings,
                        budget=budget,
                    ),
                    store=store,
                    on_progress=_on_progress,
                )
                saved = store.load(thread_id)
                if saved is not None:
                    store.save(
                        saved.model_copy(update={"live_sec_requests": budget.live_sec_requests})
                    )
                progress.progress(1.0, text="Analysis complete.")
            except (ConfigurationError, SessionQuotaError) as exc:
                st.error(public_error_message(exc))
            except Exception as exc:
                st.error(public_error_message(exc))
            else:
                st.session_state["history"] = list(
                    zip(
                        (m.content for m in turn.messages),
                        turn.results,
                        strict=False,
                    )
                )
                st.session_state["history_kill_switch"] = kill_switch
            finally:
                st.session_state["turn_in_flight"] = False

    _render_history()


if __name__ == "__main__":
    main()
