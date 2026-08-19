"""One Streamlit window: query, intent chip, tool cards, answer."""

import streamlit as st
import streamlit_shadcn_ui as ui  # type: ignore[import-untyped]

from financial_analyst_agent.config import AppMode, get_settings
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
from financial_analyst_agent.turn import TurnResult, run_turn

_GOLD_QUERY = "What was Google's net income based on their latest quarterly report?"
KILL_SWITCH_BANNER = (
    "KILL-SWITCH ON — fixture runtime (recorded facts, not live EDGAR). "
    "Say this out loud. Do not present a cassette as live."
)


def render_turn_result(result: TurnResult) -> None:
    _render_presentation(present_turn(result))


def _render_presentation(presented: Presentation) -> None:
    st.badge(presented.intent, color="blue")
    for banner in presented.banners:
        st.info(banner)
    for hit in presented.citations:
        published = f" ({hit.published})" if hit.published else ""
        st.markdown(f"- [{hit.title}]({hit.url}){published}")
    if presented.fact_card is not None:
        _render_fact_card(presented.fact_card)
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
                    ("Inputs", trace.inputs),
                    ("Outputs", trace.outputs),
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


def _render_trace_group(title: str, fields: tuple[tuple[str, str], ...]) -> None:
    st.caption(title)
    for label, value in fields:
        st.markdown(f"**{label}:** {value}")


def _render_fact_card(card: QuarterlyFactCard) -> None:
    ui.metric_card(
        label=card.metric_header,
        value=card.amount,
        description=f"{card.company_name} · {card.ticker}",
        key="lookup-fact",
    )
    st.caption(card.period_label)
    filing = f"[Filing]({card.source_url})" if card.source_url else ""
    st.markdown(f"`{card.form}` · `{card.accession_number}` · `{card.concept}` · {filing}")


def _render_table(table: DisplayTable) -> None:
    records = [
        {header: row[index] for index, header in enumerate(table.headers)} for row in table.rows
    ]
    source_header = format_field_name("source_url")
    if source_header in table.headers:
        st.dataframe(
            records,
            width="stretch",
            column_config={source_header: st.column_config.LinkColumn(display_text="Filing")},
        )
    else:
        st.dataframe(records, width="stretch")


def _render_metric_catalog() -> None:
    with st.container(border=True, gap="small"):
        st.caption("Supported metrics (SEC EDGAR)")
        columns = st.columns(len(metric_groups()))
        for column, (title, names) in zip(columns, metric_groups(), strict=True):
            with column:
                st.caption(title)
                st.markdown("  \n".join(f":gray[{name}]" for name in names))


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
    if "result" in st.session_state and st.session_state.get("result_kill_switch") != kill_switch:
        st.session_state.pop("result", None)
        st.session_state.pop("result_kill_switch", None)

    with st.form("ask"):
        query = st.text_input("Ask a question", value=_GOLD_QUERY)
        submitted = st.form_submit_button("Ask", type="primary")
    _render_metric_catalog()

    if submitted:
        if st.session_state.get("turn_in_flight"):
            st.info("A turn is already running.")
        else:
            st.session_state.pop("result", None)
            st.session_state.pop("result_kill_switch", None)
            st.session_state["turn_in_flight"] = True
            try:
                with st.spinner("Running turn…"):
                    result = run_turn(
                        query,
                        runtime_for_kill_switch(enabled=kill_switch),
                    )
            except ConfigurationError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Turn failed: {exc}")
            else:
                st.session_state["result"] = result
                st.session_state["result_kill_switch"] = kill_switch
            finally:
                st.session_state["turn_in_flight"] = False

    if "result" not in st.session_state:
        return
    render_turn_result(st.session_state["result"])


if __name__ == "__main__":
    main()
