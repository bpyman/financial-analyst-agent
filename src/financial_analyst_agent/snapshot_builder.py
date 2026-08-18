"""Rebuild the dated universe snapshot from a stub dump or FMP."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from financial_analyst_agent.config import Settings, get_settings
from financial_analyst_agent.domain.errors import ConfigurationError
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.providers.sec.tickers import (
    extract_usable_ticker_entries,
    normalize_ticker,
    parse_cik,
)
from financial_analyst_agent.universe import (
    DEFAULT_SNAPSHOT_PATH,
    US_EXCHANGES,
    UniverseCompany,
    build_universe_snapshot,
    write_universe_snapshot,
)

FMP_SCREENER_PATH = "/stable/company-screener"
FMP_EXCHANGES = ("NASDAQ", "NYSE", "AMEX")
_EXCHANGE_ALIASES: dict[str, str] = {
    "NASDAQ GLOBAL SELECT": "NASDAQ",
    "NASDAQ GLOBAL MARKET": "NASDAQ",
    "NASDAQ CAPITAL MARKET": "NASDAQ",
    "NEW YORK STOCK EXCHANGE": "NYSE",
    "NYSE ARCA": "NYSEARCA",
    "NYSE AMERICAN": "NYSEAMERICAN",
    "AMERICAN STOCK EXCHANGE": "AMEX",
}


def _ticker_cik_index(tickers_payload: dict[str, Any]) -> dict[str, str]:
    return {
        entry["ticker"]: entry["cik"] for entry in extract_usable_ticker_entries(tickers_payload)
    }


def _canonical_exchange(payload: dict[str, Any]) -> str:
    short = str(payload.get("exchangeShortName") or "").strip()
    descriptive = str(payload.get("exchange") or "").strip()
    candidate = short or descriptive
    upper = candidate.upper()
    if upper in US_EXCHANGES:
        return upper
    return _EXCHANGE_ALIASES.get(upper, candidate)


def _listing_symbol(payload: dict[str, Any]) -> str:
    return normalize_ticker(str(payload.get("ticker") or payload.get("symbol") or ""))


def _enrich_screener_row(
    payload: dict[str, Any], cik_by_ticker: Mapping[str, str]
) -> dict[str, Any] | None:
    enriched = dict(payload)
    symbol = _listing_symbol(enriched)
    if not symbol:
        return None
    sec_cik = cik_by_ticker.get(symbol)
    if sec_cik is not None:
        enriched["cik"] = sec_cik
        return enriched
    if cik_by_ticker:
        return None
    cik = parse_cik(enriched.get("cik"))
    if cik is None:
        return None
    enriched["cik"] = cik
    return enriched


def vendor_company_from_mapping(payload: dict[str, Any]) -> UniverseCompany | None:
    cik = parse_cik(payload.get("cik"))
    if cik is None:
        return None
    market_cap = _market_cap_to_decimal_str(
        payload.get("market_cap", payload.get("marketCap"))
    )
    if market_cap is None:
        return None
    name = str(payload.get("name") or payload.get("companyName") or "").strip()
    ticker = str(payload.get("ticker") or payload.get("symbol") or "").strip()
    sector = str(payload.get("sector") or "").strip()
    if not name or not ticker or not sector:
        return None
    return UniverseCompany(
        cik=cik,
        name=name,
        ticker=ticker,
        sector=sector,
        exchange=_canonical_exchange(payload),
        market_cap=Decimal(market_cap),
        is_etf=bool(payload.get("is_etf", payload.get("isEtf", payload.get("isETF", False)))),
        is_fund=bool(payload.get("is_fund", payload.get("isFund", False))),
        industry=str(payload.get("industry") or "").strip(),
    )


def companies_from_vendor_payloads(
    payloads: Sequence[Any],
    *,
    tickers_payload: dict[str, Any] | None = None,
) -> list[UniverseCompany]:
    cik_by_ticker = _ticker_cik_index(tickers_payload or {})
    rows: list[UniverseCompany] = []
    for item in payloads:
        if not isinstance(item, dict):
            continue
        enriched = _enrich_screener_row(item, cik_by_ticker)
        if enriched is None:
            continue
        company = vendor_company_from_mapping(enriched)
        if company is not None:
            rows.append(company)
    return rows


def load_vendor_rows(path: Path) -> list[UniverseCompany]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("companies", [])
    if not isinstance(raw, list):
        raise ValueError("vendor dump must be a list or an object with companies")
    return companies_from_vendor_payloads(raw)


def fetch_fmp_rows(
    api_key: str,
    client: httpx.Client | None = None,
    tickers_payload: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> list[UniverseCompany]:
    resolved = settings or get_settings()
    screener_url = f"{resolved.fmp_base_url}{FMP_SCREENER_PATH}"
    http = client or httpx.Client(timeout=60.0)
    owns_client = client is None
    raw_rows: list[Any] = []
    try:
        for exchange in FMP_EXCHANGES:
            response = http.get(
                screener_url,
                params={
                    "exchange": exchange,
                    "isEtf": "false",
                    "isFund": "false",
                    "isActivelyTrading": "true",
                    "limit": 10000,
                    "apikey": api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError(f"unexpected FMP screener payload for {exchange}")
            raw_rows.extend(payload)
        identity = tickers_payload
        if identity is None:
            identity = SECClient(resolved, client=http).get_company_tickers()
        return companies_from_vendor_payloads(raw_rows, tickers_payload=identity)
    finally:
        if owns_client:
            http.close()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild the dated universe snapshot. "
            "Ranking reads this file; it does not call FMP at request time."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Stub vendor JSON (list or {companies: [...]}). Skips live FMP.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help="Snapshot path the rank adapter reads.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.input is not None:
        rows = load_vendor_rows(args.input)
        source = "universe_snapshot"
    else:
        settings = get_settings()
        try:
            api_key = settings.require_fmp_api_key()
            settings.require_user_agent()
        except ConfigurationError as exc:
            parser.error(str(exc))
        rows = fetch_fmp_rows(api_key, settings=settings)
        source = "fmp_universe_snapshot"
    snapshot = build_universe_snapshot(
        rows,
        as_of=datetime.now(UTC),
        source=source,
    )
    if not snapshot.companies:
        raise ValueError(
            "refusing to write empty universe snapshot; "
            "check CIK identity enrichment and US operating-company filters"
        )
    written = write_universe_snapshot(snapshot, args.output)
    print(f"Wrote {len(snapshot.companies)} companies to {written}")


def _market_cap_to_decimal_str(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, ".0f")
    if isinstance(value, str):
        try:
            return str(Decimal(value))
        except InvalidOperation:
            return None
    return None


if __name__ == "__main__":
    main()
