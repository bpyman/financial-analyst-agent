"""Shared SEC company-ticker mapping and CIK validation."""

from typing import Any

from financial_analyst_agent.domain.errors import ProviderError

_MAX_CIK_DIGITS = 10


def normalize_ticker(ticker: str) -> str:
    """Canonical ticker form used across SEC identity comparisons."""
    return ticker.strip().upper()


def parse_cik(cik_raw: Any) -> str | None:
    """
    Parse a CIK as a positive integer of at most ten decimal digits.

    Returns a zero-padded ten-digit string, or None if the value is invalid.
    Values longer than ten digits are rejected rather than truncated.
    """
    if isinstance(cik_raw, bool):
        return None
    if isinstance(cik_raw, int):
        if cik_raw <= 0:
            return None
        digits = str(cik_raw)
        if len(digits) > _MAX_CIK_DIGITS:
            return None
        return digits.zfill(_MAX_CIK_DIGITS)
    if isinstance(cik_raw, str):
        if (
            not cik_raw
            or not cik_raw.isascii()
            or not cik_raw.isdigit()
            or len(cik_raw) > _MAX_CIK_DIGITS
        ):
            return None
        if int(cik_raw) <= 0:
            return None
        return cik_raw.zfill(_MAX_CIK_DIGITS)
    return None


def extract_usable_ticker_entries(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Return structurally usable ticker entries, ignoring malformed rows."""
    entries: list[dict[str, str]] = []
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        ticker = value.get("ticker")
        title = value.get("title")
        if not isinstance(ticker, str) or not isinstance(title, str):
            continue
        ticker_clean = ticker.strip()
        title_clean = title.strip()
        if not ticker_clean or not title_clean:
            continue
        cik = parse_cik(value.get("cik_str"))
        if cik is None:
            continue
        entries.append(
            {
                "ticker": normalize_ticker(ticker_clean),
                "title": title_clean,
                "cik": cik,
            }
        )
    return entries


def require_usable_company_tickers(payload: Any) -> dict[str, Any]:
    """
    Validate that a company_tickers JSON payload is a mapping with at least
    one usable ticker, title, and CIK entry.
    """
    if not isinstance(payload, dict):
        raise ProviderError(
            "company_tickers.json must be an object",
            details={"payload_type": type(payload).__name__},
        )
    entries = extract_usable_ticker_entries(payload)
    if not entries:
        raise ProviderError(
            "company_tickers.json contains no usable ticker entries",
            details={"entry_count": len(payload)},
        )
    return payload
