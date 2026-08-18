"""Deterministic company resolution from SEC ticker mapping."""

import re
from typing import Any

from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    CompanyNotFoundError,
)
from financial_analyst_agent.domain.models import Company
from financial_analyst_agent.providers.sec.aliases import ALIASES
from financial_analyst_agent.providers.sec.tickers import extract_usable_ticker_entries


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip()).casefold()


def _normalize_company_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()


def _group_by_cik(entries: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        cik = entry["cik"]
        bucket = grouped.setdefault(cik, {"title": entry["title"], "tickers": set()})
        bucket["tickers"].add(entry["ticker"])
    return grouped


def _ordered_tickers(tickers: set[str], primary_ticker: str | None = None) -> list[str]:
    sorted_tickers = sorted(tickers)
    if primary_ticker is None:
        return sorted_tickers
    primary = primary_ticker.upper()
    others = [ticker for ticker in sorted_tickers if ticker != primary]
    return [primary, *others]


def _company_from_group(
    cik: str,
    group: dict[str, Any],
    primary_ticker: str | None = None,
) -> Company:
    tickers = _ordered_tickers(group["tickers"], primary_ticker)
    return Company(cik=cik, name=group["title"], tickers=tickers)


def resolve_company(query: str, tickers_payload: dict[str, Any]) -> Company:
    """
    Resolve a company query using deterministic precedence:

    1. Exact normalized ticker (issuer-level; multiple tickers per CIK consolidate)
    2. Explicit alias registry
    3. Exact normalized legal company name
    4. Typed not-found or ambiguity error

    Ambiguity is raised only when valid matches span multiple distinct CIKs.
    Multiple ticker entries sharing one CIK represent one issuer.
    """
    normalized_query = _normalize_query(query)
    entries = extract_usable_ticker_entries(tickers_payload)
    if not entries:
        raise CompanyNotFoundError("SEC ticker mapping was empty")

    grouped = _group_by_cik(entries)

    ticker_query = normalized_query.upper()
    ticker_matches = [entry for entry in entries if entry["ticker"] == ticker_query]
    if ticker_matches:
        ticker_ciks = {entry["cik"] for entry in ticker_matches}
        if len(ticker_ciks) > 1:
            raise AmbiguousCompanyError(
                "Multiple CIKs matched ticker query",
                details={"query": query, "matches": ticker_matches},
            )
        cik = next(iter(ticker_ciks))
        return _company_from_group(cik, grouped[cik], primary_ticker=ticker_query)

    alias_target = ALIASES.get(normalized_query)
    if alias_target is not None:
        normalized_target = _normalize_company_name(alias_target)
        alias_ciks = {
            entry["cik"]
            for entry in entries
            if _normalize_company_name(entry["title"]) == normalized_target
        }
        if not alias_ciks:
            raise CompanyNotFoundError(
                f"Alias target '{alias_target}' not found in SEC ticker mapping",
                details={"query": query, "alias": alias_target},
            )
        if len(alias_ciks) > 1:
            matches = [
                entry
                for entry in entries
                if _normalize_company_name(entry["title"]) == normalized_target
            ]
            raise AmbiguousCompanyError(
                "Multiple CIKs matched alias target",
                details={"query": query, "alias": alias_target, "matches": matches},
            )
        cik = next(iter(alias_ciks))
        return _company_from_group(cik, grouped[cik])

    name_ciks = {
        entry["cik"]
        for entry in entries
        if _normalize_company_name(entry["title"]) == normalized_query
    }
    if not name_ciks:
        raise CompanyNotFoundError(
            f"Company not found for query '{query}'",
            details={"query": query},
        )
    if len(name_ciks) > 1:
        matches = [
            entry
            for entry in entries
            if _normalize_company_name(entry["title"]) == normalized_query
        ]
        raise AmbiguousCompanyError(
            "Multiple CIKs matched legal name query",
            details={"query": query, "matches": matches},
        )
    cik = next(iter(name_ciks))
    return _company_from_group(cik, grouped[cik])
