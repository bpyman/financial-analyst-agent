"""The local MCP server keeps the bounds the window's turns keep."""

import pytest

from financial_analyst_agent import mcp_server


def _tool(tool: object) -> object:
    return getattr(tool, "fn", tool)


@pytest.mark.parametrize(
    "call",
    [
        lambda: _tool(mcp_server.rank_companies)("banks", -5),
        lambda: _tool(mcp_server.rank_companies)("banks", 26),
        lambda: _tool(mcp_server.get_financials)("x" * 2001, "revenue"),
        lambda: _tool(mcp_server.compare_metrics)([], "revenue"),
        lambda: _tool(mcp_server.compare_metrics)(["AAPL"] * 26, "revenue"),
        lambda: _tool(mcp_server.explain_topic)("   "),
        lambda: _tool(mcp_server.rank_companies)("banks", True),
    ],
)
def test_out_of_bounds_calls_are_refused(call: object) -> None:
    with pytest.raises(ValueError):
        call()  # type: ignore[operator]


@pytest.mark.parametrize("tool", ["get_financials", "compare_metrics"])
def test_a_long_unknown_metric_is_refused_without_being_echoed(tool: str) -> None:
    metric = "x" * 100_000
    call = _tool(getattr(mcp_server, tool))
    with pytest.raises(ValueError) as refused:
        call("AAPL" if tool == "get_financials" else ["AAPL"], metric)  # type: ignore[operator]

    assert len(str(refused.value)) < 200


def test_a_boolean_limit_is_refused_by_the_tool_schema() -> None:
    import asyncio

    from fastmcp import Client

    async def call() -> object:
        async with Client(mcp_server.mcp) as client:
            return await client.call_tool(
                "rank_companies", {"industry": "technology", "limit": True}, raise_on_error=False
            )

    result = asyncio.run(call())

    assert result.is_error  # type: ignore[attr-defined]


@pytest.mark.parametrize("metric", ["gross_margin", "market_cap"])
def test_get_financials_takes_the_metrics_compare_metrics_takes(metric: str) -> None:
    compared = _tool(mcp_server.compare_metrics)(["MSFT"], metric)  # type: ignore[operator]
    fetched = _tool(mcp_server.get_financials)("MSFT", metric)  # type: ignore[operator]

    assert fetched == compared["rows"][0]  # type: ignore[index]
    assert fetched["value"] is not None  # type: ignore[index]


def test_an_unknown_company_in_a_comparison_says_so() -> None:
    rows = _tool(mcp_server.compare_metrics)(["MSFT", "ZZZZQQQ"], "revenue")["rows"]  # type: ignore[operator,index]

    assert rows[-1]["company_name"] == "ZZZZQQQ"
    assert rows[-1]["reason"] == "company_not_found"


def test_an_essay_quoting_numbers_its_topic_lacks_is_withheld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Essay:
        def complete_essay(self, query: str, tool_json: str = "") -> str:
            return "Revenue will grow 40% by 2030."

    class _Runtime:
        essay = _Essay()

    monkeypatch.setattr(mcp_server, "build_runtime", lambda: _Runtime())

    result = _tool(mcp_server.explain_topic)("How will AI change retail?")

    assert result["essay"] is None  # type: ignore[index]
    assert "40" in result["message"]  # type: ignore[index]
