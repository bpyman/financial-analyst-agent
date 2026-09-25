"""Exercise evidence selection and disclosure keys in real Streamlit runs."""

from streamlit.testing.v1 import AppTest


def _quarterly_evidence_app() -> None:
    from financial_analyst_agent.app import GUIDED_STORIES, render_turn_result
    from financial_analyst_agent.runtime import recorded_runtime
    from financial_analyst_agent.turn import run_turn

    result = run_turn(GUIDED_STORIES[1][1], recorded_runtime())
    render_turn_result(result)


def test_evidence_inspector_selects_the_requested_quarter() -> None:
    audience = AppTest.from_function(_quarterly_evidence_app).run(timeout=30)
    assert not audience.exception
    markdowns = [str(item.value) for item in audience.markdown]
    assert any("How this answer was fetched" in text for text in markdowns)
    lookup_headers = [
        expander.label
        for expander in audience.expander
        if expander.label.startswith("Looked up Microsoft · Revenue")
    ]
    assert len(lookup_headers) == 4
    assert len(set(lookup_headers)) == 4
    assert all("get_financials" not in label for label in lookup_headers)
    audience.selectbox[0].select_index(2).run(timeout=30)
    assert not audience.exception
    captions = [caption.value for caption in audience.caption]
    assert "Exact amount: `65585000000`" in captions
    assert "Jul 1, 2024 – Sep 30, 2024" in captions
    assert len(set(audience.selectbox[0].options)) == 4
    assert "Sep 30, 2024" in audience.selectbox[0].options[2]


def _disclosure_history_app() -> None:
    from financial_analyst_agent.app import GUIDED_STORIES, render_turn_result
    from financial_analyst_agent.runtime import recorded_runtime
    from financial_analyst_agent.turn import run_turn

    result = run_turn(GUIDED_STORIES[3][1], recorded_runtime())
    for turn_index in range(2):
        render_turn_result(result, turn_index=turn_index)


def test_disclosure_history_renders_multiple_turns() -> None:
    audience = AppTest.from_function(_disclosure_history_app).run(timeout=30)
    assert not audience.exception
    disclosures = [
        expander for expander in audience.expander
        if expander.label.endswith("· Changed")
    ]
    assert len(disclosures) == 4
