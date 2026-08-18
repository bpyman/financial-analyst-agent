"""Local FastMCP HTTP server. Same tools the turn uses in-process."""

from fastmcp import FastMCP

from financial_analyst_agent.domain.errors import UnknownIndustryError
from financial_analyst_agent.runtime import build_runtime
from financial_analyst_agent.turn import ALLOWED_METRICS, _lookup_facts
from financial_analyst_agent.turn import compare_metrics as compare_metric_rows

mcp = FastMCP("financial-analyst")


@mcp.tool()
def get_financials(company: str, metric: str) -> dict[str, object]:
    """Return the latest standalone quarterly fact for a company and metric."""
    facts = _lookup_facts(build_runtime().facts.get_financials(company, metric))
    dumped: list[dict[str, object]] = []
    for item in facts:
        payload = item.model_dump(mode="json")
        if not isinstance(payload, dict):
            raise TypeError("get_financials must serialize to an object")
        dumped.append(payload)
    if len(dumped) == 1:
        return dumped[0]
    return {"facts": dumped}


@mcp.tool()
def compare_metrics(issuers: list[str], metric: str) -> dict[str, object]:
    """Compare a reported metric or allowed margin formula across issuers."""
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


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
