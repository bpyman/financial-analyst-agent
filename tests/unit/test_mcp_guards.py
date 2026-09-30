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
    ],
)
def test_out_of_bounds_calls_are_refused(call: object) -> None:
    with pytest.raises(ValueError):
        call()  # type: ignore[operator]


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
