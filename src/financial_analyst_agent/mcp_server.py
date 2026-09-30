"""Local FastMCP HTTP server. Same tools the turn uses in-process."""

from fastmcp import FastMCP

from financial_analyst_agent.domain.errors import UnknownIndustryError
from financial_analyst_agent.graph.analysis_spec import MAX_RANKED_COMPANIES
from financial_analyst_agent.runtime import build_runtime
from financial_analyst_agent.turn import (
    ALLOWED_METRICS,
    MARKET_FORMULAS,
    SNAPSHOT_METRICS,
    _numeral_lock_extras,
    _numeral_lock_message,
    market_formula_rows,
    snapshot_compare_rows,
)
from financial_analyst_agent.turn import compare_metrics as compare_metric_rows

mcp = FastMCP("financial-analyst")

# The same bounds the window's turns keep: one question's length, one ranking's size.
MAX_TEXT_CHARS = 2000
MAX_ISSUERS = MAX_RANKED_COMPANIES


def _bounded(name: str, text: str) -> str:
    if not text.strip() or len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"{name} must be 1 to {MAX_TEXT_CHARS} characters")
    return text


@mcp.tool()
def get_financials(company: str, metric: str) -> dict[str, object]:
    """Return the latest standalone quarterly fact for a company and metric."""
    _bounded("company", company)
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
    if not issuers or len(issuers) > MAX_ISSUERS:
        raise ValueError(f"issuers must name 1 to {MAX_ISSUERS} companies")
    for issuer in issuers:
        _bounded("issuer", issuer)
    runtime = build_runtime()
    if metric in SNAPSHOT_METRICS:
        if runtime.ranking is None:
            raise RuntimeError("ranking adapter is not configured")
        rows = snapshot_compare_rows(runtime.ranking, issuers, metric)
    elif metric in MARKET_FORMULAS:
        if runtime.ranking is None:
            raise RuntimeError("ranking adapter is not configured")
        rows = market_formula_rows(runtime.facts, runtime.ranking, issuers, metric)
    else:
        rows = compare_metric_rows(runtime.facts, issuers, metric)
    return {"rows": [row.model_dump(mode="json") for row in rows]}


@mcp.tool()
def rank_companies(industry: str, limit: int = 10) -> dict[str, object]:
    """Rank US operating companies in an industry from the dated universe snapshot."""
    _bounded("industry", industry)
    if not 1 <= limit <= MAX_RANKED_COMPANIES:
        raise ValueError(f"limit must be 1 to {MAX_RANKED_COMPANIES}")
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
    """Write a labeled model-analysis essay, withheld if it quotes numbers the topic lacks."""
    _bounded("topic", topic)
    runtime = build_runtime()
    if runtime.essay is None:
        raise RuntimeError("essay completer is not configured")
    essay = runtime.essay.complete_essay(topic)
    extras = _numeral_lock_extras(essay, topic)
    if extras:
        return {"essay": None, "message": _numeral_lock_message(", ".join(extras))}
    return {"essay": essay}


@mcp.tool()
def search_news(query: str) -> dict[str, object]:
    """Search current-event news for the user query. Title and URL are required."""
    _bounded("query", query)
    runtime = build_runtime()
    if runtime.news is None:
        raise RuntimeError("news adapter is not configured")
    hits = runtime.news.search_news(query)
    return {"hits": [hit.model_dump(mode="json") for hit in hits]}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
