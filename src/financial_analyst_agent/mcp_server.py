"""Local FastMCP HTTP server. Same tools the turn uses in-process."""

from fastmcp import FastMCP

from financial_analyst_agent.domain.errors import UnknownIndustryError
from financial_analyst_agent.runtime import build_runtime
from financial_analyst_agent.turn import ALLOWED_METRICS
from financial_analyst_agent.turn import compare_metrics as compare_metric_rows

mcp = FastMCP("financial-analyst")


@mcp.tool()
def get_financials(company: str, metric: str) -> dict[str, object]:
    """Return the latest standalone quarterly fact for a company and metric."""
    fact = build_runtime().facts.get_financials(company, metric)
    payload = fact.model_dump(mode="json")
    if not isinstance(payload, dict):
        raise TypeError("get_financials must serialize to an object")
    return payload


@mcp.tool()
def compare_metrics(issuers: list[str], metric: str) -> dict[str, object]:
    """Compare a reported metric or allowed formula across issuers."""
    if metric not in ALLOWED_METRICS:
        allowed = ", ".join(ALLOWED_METRICS)
        raise ValueError(f"Unknown metric {metric!r}. Allowed: {allowed}")
    rows = compare_metric_rows(build_runtime().facts, issuers, metric)
    return {"rows": [row.model_dump(mode="json") for row in rows]}


@mcp.tool()
def rank_companies(industry: str, limit: int = 10) -> dict[str, object]:
    """Rank US operating companies in an industry from the dated universe snapshot."""
    runtime = build_runtime()
    if runtime.ranking is None:
        raise RuntimeError("ranking adapter is not configured")
    try:
        table = runtime.ranking.rank_companies(industry, limit)
    except UnknownIndustryError as exc:
        raise ValueError(str(exc)) from exc
    return {
        "as_of": table.as_of,
        "source": table.source,
        "sector": table.sector,
        "rows": [
            {
                "rank": index,
                "company_name": company.name,
                "ticker": company.ticker,
                "cik": company.cik,
                "market_cap": str(company.market_cap),
            }
            for index, company in enumerate(table.companies, start=1)
        ],
    }


@mcp.tool()
def explain_topic(topic: str) -> dict[str, object]:
    """Write a labeled model-analysis essay. The turn renderer numeral-locks the text."""
    runtime = build_runtime()
    if runtime.essay is None:
        raise RuntimeError("essay completer is not configured")
    return {"essay": runtime.essay.complete_essay(topic)}


@mcp.tool()
def search_news(query: str) -> dict[str, object]:
    """Search current-event news for the user query. Title and URL are required."""
    runtime = build_runtime()
    if runtime.news is None:
        raise RuntimeError("news adapter is not configured")
    hits = runtime.news.search_news(query)
    return {"hits": [hit.model_dump(mode="json") for hit in hits]}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
