"""The old Streamlit Community Cloud URL: a single "This demo has moved" page.

Links sent out before the cutover point here. The page reads the new address
from the ``DEMO_URL`` secret. Community Cloud exports top-level string secrets
as environment variables, so a local run can set the variable instead. Until
the new demo is live, the button opens the project on GitHub and says so.
"""

from __future__ import annotations

import os

import streamlit as st

GITHUB_URL = "https://github.com/bpyman/financial-analyst-agent"


def demo_url() -> str | None:
    """The new demo's address, or None while it is unset or not an https URL."""
    url = os.environ.get("DEMO_URL", "").strip()
    return url if url.startswith("https://") else None


st.set_page_config(
    page_title="Financial Analyst Agent has moved",
    page_icon=":material/open_in_new:",
    layout="centered",
    initial_sidebar_state="collapsed",
)

url = demo_url()

st.space("large")
st.caption("FINANCIAL ANALYST AGENT")
st.title("This demo has moved", anchor=False)
if url:
    st.write("The analyst now runs at a new address. Update any bookmarks to it.")
    st.link_button("Open the new demo", url, type="primary", icon=":material/arrow_forward:")
else:
    st.write("The new address is not live yet. Until it is, the project and a walkthrough are on GitHub.")
    st.link_button("View the project on GitHub", GITHUB_URL, type="primary", icon=":material/arrow_forward:")
