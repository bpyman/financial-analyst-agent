"""One Streamlit window: query, intent chip, tool cards, answer."""

import streamlit as st

from financial_analyst_agent.config import AppMode, get_settings
from financial_analyst_agent.runtime import build_runtime
from financial_analyst_agent.turn import RendererKind, Runtime, run_turn

_GOLD_QUERY = "What was Google's net income based on their latest quarterly report?"


@st.cache_resource
def _runtime() -> Runtime:
    return build_runtime()


def main() -> None:
    st.set_page_config(page_title="Financial analyst agent", layout="wide")
    st.title("Financial analyst agent")
    settings = get_settings()
    if settings.app_mode is AppMode.FIXTURE:
        st.caption("Fixture runtime — recorded facts, not live EDGAR.")
    else:
        st.caption("Live SEC — companyfacts XBRL, not a fixture cassette.")

    query = st.text_input("Question", value=_GOLD_QUERY)
    if not st.button("Ask", type="primary") and "result" not in st.session_state:
        return

    result = run_turn(query, _runtime())
    st.session_state["result"] = result

    st.markdown(f"**Intent:** `{result.intent}`")

    for banner in result.banners:
        st.info(banner)

    for trace in result.tool_traces:
        with st.expander(f"Tool: {trace.tool}", expanded=True):
            st.json({"args": trace.args, "provenance": trace.provenance})

    if result.renderer is RendererKind.REFUSE:
        st.error(result.message)
        return
    if result.renderer is RendererKind.TABLE:
        st.dataframe(
            [row.model_dump(mode="json") for row in result.table_rows],
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
