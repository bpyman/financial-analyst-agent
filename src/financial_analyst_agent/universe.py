"""Dated universe snapshot: membership freeze for ranking."""

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.serialization import DecimalStr

DEFAULT_SNAPSHOT_PATH = Path(__file__).parent / "data" / "universe_snapshot.json"
_INELIGIBLE_ISSUERS_PATH = Path(__file__).parent / "data" / "ineligible_issuers.json"

US_EXCHANGES: frozenset[str] = frozenset(
    {
        "NYSE",
        "NASDAQ",
        "AMEX",
        "NYSEARCA",
        "NYSEAMERICAN",
        "NASDAQGS",
        "NASDAQGM",
        "NASDAQCM",
    }
)

INDUSTRY_ALIASES: dict[str, str] = {
    "healthcare": "Healthcare",
    "health care": "Healthcare",
    "finance": "Financial Services",
    "financials": "Financial Services",
    "financial services": "Financial Services",
    "technology": "Technology",
    "tech": "Technology",
    "information technology": "Technology",
}

# NYSE/NASDAQ product suffixes: preferreds, units, warrants, rights — not common shares.
_NON_COMMON_TICKER = re.compile(
    r"(?:-P[A-Z]?|-U(?:N)?|-W(?:S|T)?|-R)$",
    re.IGNORECASE,
)
# FMP puts the instrument description in companyName; there is no securityType field.
_INSTRUMENT_TITLE = re.compile(
    r"\bpfd\b|preferred\s+stock|perpetual\s+preferred|\bwarrants?\b|"
    r"collateral\s+tr(?:ust|\b)|tr\s+secs|capital\s+trust|"
    r"notes?\s+due|senior\s+notes|"
    r"\d+(?:\.\d+)?\s*%|"
    r"\b(?:sr|senior)\s+nts?\b|"
    r"jr\s+sub(?:ordinated)?\s+nts?\b|"
    r"index\s+plus\s+trust|"
    r"\btrust\s+(?:for|series)\b|"
    r"\bstrats\b",
    re.IGNORECASE,
)
# Empirically vehicle-dominated FMP industries. Asset Management is not in this
# set: it mixes BlackRock with BDCs. Residual lookalikes are CIKs in
# ineligible_issuers.json (ADR 0001).
_NON_OPERATING_INDUSTRIES = frozenset(
    {
        "shell companies",
        "financial - conglomerates",
    }
)


def _ineligible_issuer_ciks(path: Path = _INELIGIBLE_ISSUERS_PATH) -> frozenset[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(str(issuer["cik"]) for issuer in payload["issuers"])


INELIGIBLE_ISSUER_CIKS = _ineligible_issuer_ciks()


class UniverseCompany(BaseModel):
    cik: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    name: str
    ticker: str
    sector: str
    exchange: str = ""
    market_cap: DecimalStr
    is_etf: bool = False
    is_fund: bool = False
    industry: str = ""


def is_common_operating_listing(company: UniverseCompany) -> bool:
    """True for common shares of operating issuers, not funds, shells, or structured products."""
    return _is_common_share(company) and _is_operating_issuer(company)


def _is_common_share(company: UniverseCompany) -> bool:
    if company.is_etf or company.is_fund:
        return False
    if _NON_COMMON_TICKER.search(company.ticker.strip()):
        return False
    return _INSTRUMENT_TITLE.search(company.name) is None


def _is_operating_issuer(company: UniverseCompany) -> bool:
    if company.cik in INELIGIBLE_ISSUER_CIKS:
        return False
    return company.industry.strip().casefold() not in _NON_OPERATING_INDUSTRIES


def preferred_listing(rows: Sequence[UniverseCompany]) -> UniverseCompany:
    """Pick the common operating listing for one CIK.

    Note/preferred tickers are often a longer extension of the common symbol
    (SO vs SOMN) and can carry inflated vendor market caps.
    """
    listings = list(rows)
    if len(listings) == 1:
        return listings[0]
    tickers = [row.ticker.strip().upper() for row in listings]
    stems = [
        row
        for row, ticker in zip(listings, tickers, strict=True)
        if not any(ticker != other and ticker.startswith(other) for other in tickers)
    ]
    if not stems:
        stems = listings
    return min(stems, key=lambda row: (len(row.ticker), -row.market_cap))


class UniverseSnapshot(BaseModel):
    as_of: datetime
    source: str = "universe_snapshot"
    companies: list[UniverseCompany] = Field(default_factory=list)


def load_universe_snapshot(path: Path | None = None) -> UniverseSnapshot:
    snapshot_path = path or DEFAULT_SNAPSHOT_PATH
    return UniverseSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))


def write_universe_snapshot(snapshot: UniverseSnapshot, path: Path | None = None) -> Path:
    snapshot_path = path or DEFAULT_SNAPSHOT_PATH
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        _snapshot_json(snapshot) + "\n",
        encoding="utf-8",
    )
    return snapshot_path


def _snapshot_json(snapshot: UniverseSnapshot) -> str:
    payload = snapshot.model_dump(mode="json")
    for company in payload["companies"]:
        if not company.get("industry"):
            company.pop("industry", None)
    return json.dumps(payload, indent=2)


def build_universe_snapshot(
    rows: Sequence[UniverseCompany],
    *,
    as_of: datetime,
    source: str = "universe_snapshot",
) -> UniverseSnapshot:
    """Filter a vendor dump into the dated operating-company freeze the rank adapter reads."""
    eligible = [
        row
        for row in rows
        if is_common_operating_listing(row)
        and row.exchange.upper() in US_EXCHANGES
        and row.sector
    ]
    eligible.sort(key=lambda row: row.market_cap, reverse=True)
    by_cik: dict[str, list[UniverseCompany]] = defaultdict(list)
    for row in eligible:
        by_cik[row.cik].append(row)
    companies = [preferred_listing(group) for group in by_cik.values()]
    companies.sort(key=lambda row: row.market_cap, reverse=True)
    return UniverseSnapshot(as_of=as_of, source=source, companies=companies)


def resolve_industry(industry: str, snapshot: UniverseSnapshot) -> str | None:
    normalized = " ".join(industry.strip().casefold().split())
    if normalized in INDUSTRY_ALIASES:
        return INDUSTRY_ALIASES[normalized]
    sectors = {company.sector for company in snapshot.companies}
    for sector in sectors:
        if sector.casefold() == normalized:
            return sector
    return None


def allowed_industry_names(snapshot: UniverseSnapshot) -> tuple[str, ...]:
    aliases = ("finance", "healthcare", "technology")
    sectors = tuple(sorted({company.sector for company in snapshot.companies}))
    seen: list[str] = []
    for name in (*aliases, *sectors):
        if name not in seen:
            seen.append(name)
    return tuple(seen)
