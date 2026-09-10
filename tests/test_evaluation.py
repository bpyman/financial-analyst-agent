"""The evaluation suite produces a checked-in scorecard shape."""

from financial_analyst_agent.evaluation import run_suite


def test_fixture_scorecard_covers_required_categories() -> None:
    payload = run_suite()
    categories = {row["category"] for row in payload["cases"]}
    assert {
        "intent_routing",
        "ambiguity_refusal",
        "stateful_follow_up",
        "numeral_lock",
        "filing_change",
    } <= categories
    assert payload["case_count"] >= 8
    assert payload["pass_rate"] >= 0.75
    assert "p50_ms" in payload
    assert payload["live_cost_usd"] == 0.0
