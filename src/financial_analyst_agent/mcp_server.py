"""Local FastMCP HTTP server. Same get_financials implementation the turn uses."""

from fastmcp import FastMCP

from financial_analyst_agent.runtime import build_runtime

mcp = FastMCP("financial-analyst")


@mcp.tool()
def get_financials(company: str, metric: str) -> dict[str, object]:
    """Return the latest standalone quarterly fact for a company and metric."""
    fact = build_runtime().facts.get_financials(company, metric)
    dumped = fact.model_dump(mode="json")
    if not isinstance(dumped, dict):
        raise TypeError("get_financials must serialize to an object")
    return dumped


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
