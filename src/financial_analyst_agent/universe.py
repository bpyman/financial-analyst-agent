"""Dated universe snapshot: membership freeze for ranking."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.serialization import DecimalStr

DEFAULT_SNAPSHOT_PATH = Path(__file__).parent / "data" / "universe_snapshot.json"

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


class UniverseCompany(BaseModel):
    cik: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    name: str
    ticker: str
    sector: str
    exchange: str = ""
    market_cap: DecimalStr
    is_etf: bool = False
    is_fund: bool = False


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
        snapshot.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot_path


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
        if not row.is_etf
        and not row.is_fund
        and row.exchange.upper() in US_EXCHANGES
        and row.sector
    ]
    eligible.sort(key=lambda row: row.market_cap, reverse=True)
    by_cik: dict[str, UniverseCompany] = {}
    for row in eligible:
        if row.cik not in by_cik:
            by_cik[row.cik] = row
    return UniverseSnapshot(as_of=as_of, source=source, companies=list(by_cik.values()))


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
