"""Rebuild the dated universe snapshot from a stub dump or FMP."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from financial_analyst_agent.universe import (
    DEFAULT_SNAPSHOT_PATH,
    UniverseCompany,
    build_universe_snapshot,
    write_universe_snapshot,
)

FMP_SCREENER_URL = "https://financialmodelingprep.com/api/v3/stock-screener"
FMP_EXCHANGES = ("NASDAQ", "NYSE", "AMEX")


def vendor_company_from_mapping(payload: dict[str, Any]) -> UniverseCompany | None:
    cik_raw = payload.get("cik")
    if cik_raw is None:
        return None
    cik = str(cik_raw).strip()
    if not cik.isdigit():
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
    exchange = str(
        payload.get("exchange") or payload.get("exchangeShortName") or ""
    ).strip()
    return UniverseCompany(
        cik=cik.zfill(10),
        name=name,
        ticker=ticker,
        sector=sector,
        exchange=exchange,
        market_cap=Decimal(market_cap),
        is_etf=bool(payload.get("is_etf", payload.get("isEtf", payload.get("isETF", False)))),
        is_fund=bool(payload.get("is_fund", payload.get("isFund", False))),
    )


def load_vendor_rows(path: Path) -> list[UniverseCompany]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("companies", [])
    if not isinstance(raw, list):
        raise ValueError("vendor dump must be a list or an object with companies")
    rows: list[UniverseCompany] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        company = vendor_company_from_mapping(item)
        if company is not None:
            rows.append(company)
    return rows


def fetch_fmp_rows(api_key: str, client: httpx.Client | None = None) -> list[UniverseCompany]:
    http = client or httpx.Client(timeout=60.0)
    owns_client = client is None
    rows: list[UniverseCompany] = []
    try:
        for exchange in FMP_EXCHANGES:
            response = http.get(
                FMP_SCREENER_URL,
                params={
                    "exchange": exchange,
                    "limit": 10000,
                    "apikey": api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError(f"unexpected FMP screener payload for {exchange}")
            for item in payload:
                if not isinstance(item, dict):
                    continue
                company = vendor_company_from_mapping(item)
                if company is not None:
                    rows.append(company)
    finally:
        if owns_client:
            http.close()
    return rows


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
        api_key = os.environ.get("FMP_API_KEY", "").strip()
        if not api_key:
            parser.error("FMP_API_KEY is required unless --input is provided")
        rows = fetch_fmp_rows(api_key)
        source = "fmp_universe_snapshot"
    snapshot = build_universe_snapshot(
        rows,
        as_of=datetime.now(UTC),
        source=source,
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
