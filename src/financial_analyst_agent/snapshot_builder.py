"""Rebuild the dated universe snapshot from a stub dump or FMP."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

import httpx

from financial_analyst_agent.config import Settings, get_settings
from financial_analyst_agent.domain.errors import ConfigurationError, ProviderError
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.providers.sec.submissions import files_quarterly_reports
from financial_analyst_agent.providers.sec.tickers import (
    extract_usable_ticker_entries,
    normalize_ticker,
    parse_cik,
)
from financial_analyst_agent.universe import (
    DEFAULT_SNAPSHOT_PATH,
    US_EXCHANGES,
    UniverseCompany,
    UniverseSnapshot,
    build_universe_snapshot,
    load_universe_snapshot,
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


def primary_tickers(tickers_payload: dict[str, Any]) -> dict[str, str]:
    """The ticker SEC lists first for each CIK, which is its common share."""
    primary: dict[str, str] = {}
    for entry in extract_usable_ticker_entries(tickers_payload):
        primary.setdefault(entry["cik"], entry["ticker"])
    return primary


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
    market_cap = _market_cap_to_decimal_str(payload.get("market_cap", payload.get("marketCap")))
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


class SubmissionsSource(Protocol):
    def get_submissions(self, cik: str) -> dict[str, Any]: ...


def annotate_filers(
    snapshot: UniverseSnapshot,
    sec: SubmissionsSource,
    *,
    workers: int = 4,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[UniverseSnapshot, list[str]]:
    """Set ``files_quarterly`` from each company's SEC submissions.

    Membership, order, ``as_of``, and market caps are untouched. A company whose
    submissions cannot be read keeps its current flag; its CIK is returned so
    the caller can report it. Workers share the SEC client's rate limiter, so
    more of them only hide request latency.
    """

    def classify(company: UniverseCompany) -> bool | None:
        try:
            return files_quarterly_reports(sec.get_submissions(company.cik))
        except ProviderError:
            return None

    total = len(snapshot.companies)
    companies: list[UniverseCompany] = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, (company, flag) in enumerate(
            zip(snapshot.companies, pool.map(classify, snapshot.companies), strict=True),
            start=1,
        ):
            if flag is None:
                failed.append(company.cik)
                companies.append(company)
            else:
                companies.append(company.model_copy(update={"files_quarterly": flag}))
            if progress is not None:
                progress(done, total)
    return snapshot.model_copy(update={"companies": companies}), failed


def _sec_submissions_source(settings: Settings) -> CachingSECDataSource:
    cache_dir = settings.sec_cache_dir or Path(".cache") / "sec"
    return CachingSECDataSource(SECClient(settings), Path(cache_dir))


def _print_progress(done: int, total: int) -> None:
    if done % 250 == 0 or done == total:
        print(f"Checked SEC filings for {done}/{total} companies", flush=True)


def _annotate_with_sec(snapshot: UniverseSnapshot, settings: Settings) -> UniverseSnapshot:
    sec = _sec_submissions_source(settings)
    try:
        annotated, failed = annotate_filers(snapshot, sec, progress=_print_progress)
    finally:
        sec.close()
    flagged = sum(1 for company in annotated.companies if not company.files_quarterly)
    print(f"{flagged} companies are foreign filers with no 10-Qs; ranking skips them")
    if failed:
        print(f"Could not read SEC submissions for {len(failed)} CIKs: {', '.join(failed)}")
    return annotated


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
    parser.add_argument(
        "--annotate-filers",
        action="store_true",
        help=(
            "Re-check which companies in the existing --output snapshot file 10-Qs, "
            "using SEC submissions only. Keeps as_of, membership, and market caps."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.annotate_filers:
        if args.input is not None:
            parser.error("--annotate-filers reads --output; it does not take --input")
        settings = get_settings()
        try:
            settings.require_user_agent()
        except ConfigurationError as exc:
            parser.error(str(exc))
        existing = load_universe_snapshot(args.output)
        written = write_universe_snapshot(_annotate_with_sec(existing, settings), args.output)
        print(f"Annotated {len(existing.companies)} companies in {written}")
        return
    primary: dict[str, str] = {}
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
        sec = SECClient(settings)
        try:
            identity = sec.get_company_tickers()
        finally:
            sec.close()
        rows = fetch_fmp_rows(api_key, tickers_payload=identity, settings=settings)
        primary = primary_tickers(identity)
        source = "fmp_universe_snapshot"
    snapshot = build_universe_snapshot(
        rows,
        as_of=datetime.now(UTC),
        source=source,
        primary_tickers=primary,
    )
    if not snapshot.companies:
        raise ValueError(
            "refusing to write empty universe snapshot; "
            "check CIK identity enrichment and US operating-company filters"
        )
    if args.input is None:
        # A stub dump is an offline rebuild; only the live build asks EDGAR.
        snapshot = _annotate_with_sec(snapshot, settings)
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
