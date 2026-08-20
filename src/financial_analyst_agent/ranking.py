"""Rank companies from a dated universe snapshot."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from financial_analyst_agent.domain.errors import CompanyNotFoundError, UnknownIndustryError
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.universe import (
    UniverseCompany,
    UniverseSnapshot,
    allowed_industry_names,
    is_common_operating_listing,
    load_universe_snapshot,
    preferred_listing,
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
            if company.sector == sector and is_common_operating_listing(company)
        ]
        by_cik: dict[str, list[UniverseCompany]] = {}
        for company in ranked:
            by_cik.setdefault(company.cik, []).append(company)
        selected = [preferred_listing(group) for group in by_cik.values()]
        selected.sort(key=lambda company: company.market_cap, reverse=True)
        selected = selected[:limit]
        return RankTable(
            as_of=_format_as_of(self._snapshot.as_of),
            source=self._snapshot.source,
            sector=sector,
            companies=tuple(selected),
        )

    def snapshot_as_of(self) -> str:
        return _format_as_of(self._snapshot.as_of)

    def snapshot_source(self) -> str:
        return self._snapshot.source

    def lookup_member(self, company: str) -> UniverseCompany:
        resolved = resolve_company(company, self._operating_ticker_payload())
        listings = [
            row
            for row in self._snapshot.companies
            if row.cik == resolved.cik and is_common_operating_listing(row)
        ]
        if not listings:
            raise CompanyNotFoundError(
                f"Company not found for query '{company}'",
                details={"query": company},
            )
        return preferred_listing(listings)

    def _operating_ticker_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for index, company in enumerate(self._snapshot.companies):
            if not is_common_operating_listing(company):
                continue
            payload[str(index)] = {
                "ticker": company.ticker,
                "title": company.name,
                "cik_str": int(company.cik),
            }
        return payload


def _format_as_of(value: datetime) -> str:
    iso = value.isoformat()
    if iso.endswith("+00:00"):
        return iso
    if iso.endswith("Z"):
        return iso.replace("Z", "+00:00")
    return iso
