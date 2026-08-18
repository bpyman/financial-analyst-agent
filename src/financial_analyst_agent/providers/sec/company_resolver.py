"""Deterministic company resolution from SEC ticker mapping."""

import re
from typing import Any

from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    CompanyNotFoundError,
)
from financial_analyst_agent.domain.models import Company
from financial_analyst_agent.providers.sec.aliases import ALIASES
from financial_analyst_agent.providers.sec.tickers import extract_usable_ticker_entries, parse_cik

_LEGAL_SUFFIXES = re.compile(
    r"(?:,)?\s+(?:"
    r"incorporated|inc|corporation|corp|companies|company|co|"
    r"limited|ltd|holdings|holding|group|llc|l\.l\.c|"
    r"lp|l\.p|plc|s\.a|sa|n\.v|nv|a\.g|ag|"
    r"class\s+[a-z]|ordinary\s+shares?"
    r")\.?$",
    re.IGNORECASE,
)
_MIN_CORE_PREFIX_LEN = 4


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _core_company_name(name: str) -> str:
    """Strip legal suffixes and punctuation so successor titles match operating names."""
    text = _normalize_text(name)
    while True:
        stripped = _LEGAL_SUFFIXES.sub("", text).strip(" ,.")
        if stripped == text:
            break
        text = stripped
    return re.sub(r"[^a-z0-9]+", "", text)


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


def _unique_cik(
    query: str,
    entries: list[dict[str, str]],
    ciks: set[str],
    message: str,
) -> str:
    if len(ciks) > 1:
        matches = [entry for entry in entries if entry["cik"] in ciks]
        raise AmbiguousCompanyError(
            message,
            details={"query": query, "matches": matches},
        )
    return next(iter(ciks))


def _name_match_ciks(query: str, entries: list[dict[str, str]]) -> set[str]:
    normalized_query = _normalize_text(query)
    exact = {
        entry["cik"]
        for entry in entries
        if _normalize_text(entry["title"]) == normalized_query
    }
    if exact:
        return exact
    query_core = _core_company_name(query)
    if not query_core:
        return set()
    core_matches = {
        entry["cik"]
        for entry in entries
        if _core_company_name(entry["title"]) == query_core
    }
    if core_matches:
        return core_matches
    if len(query_core) < _MIN_CORE_PREFIX_LEN:
        return set()
    return {
        entry["cik"]
        for entry in entries
        if (title_core := _core_company_name(entry["title"]))
        and title_core.startswith(query_core)
    }


def resolve_company(query: str, tickers_payload: dict[str, Any]) -> Company:
    """
    Resolve a company query using deterministic precedence:

    1. Exact normalized ticker (issuer-level; multiple tickers per CIK consolidate)
    2. Direct CIK
    3. Explicit alias registry
    4. Legal name, then suffix-stripped core name, then unique core prefix
    5. Typed not-found or ambiguity error

    Ambiguity is raised only when valid matches span multiple distinct CIKs.
    Multiple ticker entries sharing one CIK represent one issuer.
    Core-name matching covers successor/holdings titles (ExxonMobil vs
    ExxonMobil Holdings Corp) without a per-issuer alias list.
    """
    normalized_query = _normalize_text(query)
    entries = extract_usable_ticker_entries(tickers_payload)
    if not entries:
        raise CompanyNotFoundError("SEC ticker mapping was empty")

    grouped = _group_by_cik(entries)

    ticker_query = normalized_query.upper()
    ticker_matches = [entry for entry in entries if entry["ticker"] == ticker_query]
    if ticker_matches:
        ticker_ciks = {entry["cik"] for entry in ticker_matches}
        cik = _unique_cik(
            query, ticker_matches, ticker_ciks, "Multiple CIKs matched ticker query"
        )
        return _company_from_group(cik, grouped[cik], primary_ticker=ticker_query)

    cik_query = parse_cik(query.strip())
    if cik_query is not None and cik_query in grouped:
        return _company_from_group(cik_query, grouped[cik_query])

    alias_target = ALIASES.get(normalized_query)
    if alias_target is not None:
        alias_ciks = _name_match_ciks(alias_target, entries)
        if not alias_ciks:
            raise CompanyNotFoundError(
                f"Alias target '{alias_target}' not found in SEC ticker mapping",
                details={"query": query, "alias": alias_target},
            )
        cik = _unique_cik(
            query, entries, alias_ciks, "Multiple CIKs matched alias target"
        )
        return _company_from_group(cik, grouped[cik])

    name_ciks = _name_match_ciks(query, entries)
    if not name_ciks:
        raise CompanyNotFoundError(
            f"Company not found for query '{query}'",
            details={"query": query},
        )
    cik = _unique_cik(
        query, entries, name_ciks, "Multiple CIKs matched legal name query"
    )
    return _company_from_group(cik, grouped[cik])
