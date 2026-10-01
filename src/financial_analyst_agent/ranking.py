"""Rank companies from a dated universe snapshot."""

from dataclasses import dataclass
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
    resolve_industry_group,
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
        # The snapshot is immutable, so the operating-listing views are built once
        # instead of rescanning thousands of rows on every lookup.
        self._operating = tuple(
            company for company in snapshot.companies if is_common_operating_listing(company)
        )
        self._listings_by_cik: dict[str, list[UniverseCompany]] = {}
        for company in self._operating:
            self._listings_by_cik.setdefault(company.cik, []).append(company)
        self._ticker_payload: dict[str, Any] = {
            str(index): {
                "ticker": company.ticker,
                "title": company.name,
                "cik_str": int(company.cik),
            }
            for index, company in enumerate(snapshot.companies)
            if is_common_operating_listing(company)
        }

    @classmethod
    def from_path(cls, path: Path | None = None) -> "SnapshotRanking":
        return cls(load_universe_snapshot(path))

    def rank_companies(self, industry: str, limit: int) -> RankTable:
        group = resolve_industry_group(industry, self._snapshot)
        if group is None:
            allowed = ", ".join(allowed_industry_names(self._snapshot))
            raise UnknownIndustryError(
                f"Unknown industry {industry!r}. Allowed: {allowed}",
            )
        ranked = [
            company
            for company in self._operating
            if group.includes(company) and company.files_quarterly
        ]
        by_cik: dict[str, list[UniverseCompany]] = {}
        for company in ranked:
            by_cik.setdefault(company.cik, []).append(company)
        selected = [preferred_listing(group) for group in by_cik.values()]
        selected.sort(key=lambda company: company.market_cap, reverse=True)
        selected = selected[: max(limit, 1)]
        return RankTable(
            as_of=self.snapshot_as_of(),
            source=self._snapshot.source,
            sector=group.label,
            companies=tuple(selected),
        )

    def snapshot_companies(self) -> tuple[UniverseCompany, ...]:
        return tuple(self._snapshot.companies)

    def snapshot_as_of(self) -> str:
        return self._snapshot.as_of.isoformat()

    def snapshot_source(self) -> str:
        return self._snapshot.source

    def lookup_member(self, company: str) -> UniverseCompany:
        resolved = resolve_company(company, self._ticker_payload)
        listings = self._listings_by_cik.get(resolved.cik)
        if not listings:
            raise CompanyNotFoundError(
                f"Company not found for query '{company}'",
                details={"query": company},
            )
        return preferred_listing(listings)

    def peers(
        self, cik: str, *, exclude: frozenset[str] = frozenset(), limit: int = 3
    ) -> tuple[UniverseCompany, ...]:
        """The largest other companies in ``cik``'s industry, for "add a peer" suggestions."""
        own = next((row for row in self._snapshot.companies if row.cik == cik), None)
        if own is None or not own.industry:
            return ()
        seen = {cik, *exclude}
        found: list[UniverseCompany] = []
        for row in self._operating:
            if row.industry == own.industry and row.cik not in seen and row.files_quarterly:
                seen.add(row.cik)
                found.append(row)
        found.sort(key=lambda row: row.market_cap, reverse=True)
        return tuple(found[:limit])
