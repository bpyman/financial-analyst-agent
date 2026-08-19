"""One Streamlit window: query, intent chip, tool cards, answer."""

import streamlit as st

from financial_analyst_agent.config import AppMode, get_settings
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.runtime import runtime_for_kill_switch
from financial_analyst_agent.turn import RendererKind, TurnResult, run_turn

_GOLD_QUERY = "What was Google's net income based on their latest quarterly report?"
KILL_SWITCH_BANNER = (
    "KILL-SWITCH ON — fixture runtime (recorded facts, not live EDGAR). "
    "Say this out loud. Do not present a cassette as live."
)


def render_turn_result(result: TurnResult) -> None:
    st.markdown(f"**Intent:** `{result.intent}`")

    for banner in result.banners:
        st.info(banner)

    for hit in result.citations:
        published = f" ({hit.published})" if hit.published else ""
        st.markdown(f"- [{hit.title}]({hit.url}){published}")

    for trace in result.tool_traces:
        with st.expander(f"Tool: {trace.tool}", expanded=True):
            st.json({"args": trace.args, "provenance": trace.provenance})

    if result.renderer is RendererKind.REFUSE:
        st.error(result.message)
        return
    if result.renderer is RendererKind.ESSAY:
        st.markdown(result.essay)
        return
    if result.renderer is RendererKind.TABLE:
        st.dataframe(
            [row.model_dump(mode="json") for row in result.table_rows],
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(page_title="Financial analyst agent", layout="wide")
    st.title("Financial analyst agent")
    settings = get_settings()
    kill_switch = st.sidebar.toggle(
        "Fixture kill-switch",
        value=settings.app_mode is AppMode.FIXTURE,
        help="Recorded adapters. Announce this if you use it.",
    )
    if kill_switch:
        st.warning(KILL_SWITCH_BANNER)
    else:
        st.caption("Live runtime — SEC XBRL, OpenAI planner, Tavily news.")

    query = st.text_input("Question", value=_GOLD_QUERY)
    if st.button("Ask", type="primary"):
        try:
            result = run_turn(query, runtime_for_kill_switch(enabled=kill_switch))
        except ConfigurationError as exc:
            st.error(str(exc))
            return
        st.session_state["result"] = result

    cached_result: TurnResult | None = st.session_state.get("result")
    if cached_result is None:
        return
    render_turn_result(cached_result)


if __name__ == "__main__":
    main()
