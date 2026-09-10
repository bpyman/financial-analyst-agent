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
    by_id = {row["id"]: row for row in payload["cases"]}
    assert by_id["lookup_msft_pretax"]["passed"]
    assert by_id["compare_tsla_gm"]["passed"]
    assert by_id["follow_up_add_apple"]["passed"]
    assert by_id["numeral_lock_invented_number"]["passed"]
    assert by_id["filing_change_mda"]["passed"]
    assert payload["case_count"] >= 9
    assert payload["pass_rate"] == 1.0
    assert "p50_ms" in payload
    assert payload["live_cost_usd"] == 0.0
