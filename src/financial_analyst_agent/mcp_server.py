"""Local FastMCP HTTP server. Same tools the turn uses in-process."""

from fastmcp import FastMCP

from financial_analyst_agent.runtime import build_runtime
from financial_analyst_agent.turn import ALLOWED_METRICS
from financial_analyst_agent.turn import compare_metrics as compare_metric_rows

mcp = FastMCP("financial-analyst")


@mcp.tool()
def get_financials(company: str, metric: str) -> dict[str, object]:
    """Return the latest standalone quarterly fact for a company and metric."""
    fact = build_runtime().facts.get_financials(company, metric)
    dumped = fact.model_dump(mode="json")
    if not isinstance(dumped, dict):
        raise TypeError("get_financials must serialize to an object")
    return dumped


@mcp.tool()
def compare_metrics(issuers: list[str], metric: str) -> dict[str, object]:
    """Compare a reported metric or allowed margin formula across issuers."""
    if metric not in ALLOWED_METRICS:
        allowed = ", ".join(ALLOWED_METRICS)
        raise ValueError(f"Unknown metric {metric!r}. Allowed: {allowed}")
    rows = compare_metric_rows(build_runtime().facts, issuers, metric)
    return {"rows": [row.model_dump(mode="json") for row in rows]}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
