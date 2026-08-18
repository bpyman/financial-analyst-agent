"""Rank companies from a dated universe snapshot."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from financial_analyst_agent.domain.errors import UnknownIndustryError
from financial_analyst_agent.universe import (
    UniverseCompany,
    UniverseSnapshot,
    allowed_industry_names,
    load_universe_snapshot,
    resolve_industry,
)


@dataclass(frozen=True)
class RankTable:
    as_of: str
    source: str
    sector: str
    companies: tuple[UniverseCompany, ...]


class SnapshotRanking:
    """Sort a checked-in snapshot. Membership does not change at request time."""

    def __init__(self, snapshot: UniverseSnapshot) -> None:
        self._snapshot = snapshot

    @classmethod
    def from_path(cls, path: Path | None = None) -> "SnapshotRanking":
        return cls(load_universe_snapshot(path))

    def rank_companies(self, industry: str, limit: int) -> RankTable:
        sector = resolve_industry(industry, self._snapshot)
        if sector is None:
            allowed = ", ".join(allowed_industry_names(self._snapshot))
            raise UnknownIndustryError(
                f"Unknown industry {industry!r}. Allowed: {allowed}",
            )
        ranked = [
            company
            for company in self._snapshot.companies
            if company.sector == sector and not company.is_etf and not company.is_fund
        ]
        ranked.sort(key=lambda company: company.market_cap, reverse=True)
        seen_ciks: set[str] = set()
        selected: list[UniverseCompany] = []
        for company in ranked:
            if company.cik in seen_ciks:
                continue
            seen_ciks.add(company.cik)
            selected.append(company)
            if len(selected) >= limit:
                break
        return RankTable(
            as_of=_format_as_of(self._snapshot.as_of),
            source=self._snapshot.source,
            sector=sector,
            companies=tuple(selected),
        )


def _format_as_of(value: datetime) -> str:
    iso = value.isoformat()
    if iso.endswith("+00:00"):
        return iso
    if iso.endswith("Z"):
        return iso.replace("Z", "+00:00")
    return iso
