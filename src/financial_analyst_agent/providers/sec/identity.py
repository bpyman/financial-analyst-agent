"""Shared issuer-identity validation for CIK-addressed SEC endpoints."""

from typing import Any

from financial_analyst_agent.domain.errors import DataIntegrityError, InvalidParameterError
from financial_analyst_agent.providers.sec.tickers import parse_cik


def require_requested_cik(cik: str) -> str:
    """Normalize a caller-supplied CIK. A malformed request is the caller's error."""
    requested = parse_cik(cik)
    if requested is None:
        raise InvalidParameterError(
            "cik must be a positive decimal CIK of at most ten digits",
            details={"input": "cik"},
        )
    return requested


def require_matching_payload_cik(payload: dict[str, Any], cik: str, *, message: str) -> str:
    """
    Require a payload to report the requested issuer CIK.

    Both the requested and the reported CIK pass through the strict ``parse_cik``
    helper, so every CIK-addressed endpoint compares identity the same way. A missing,
    malformed, or mismatched CIK is an identity violation and raises DataIntegrityError:
    it can never degrade into an availability failure or a partial item result.
    """
    requested = require_requested_cik(cik)
    reported = parse_cik(payload.get("cik"))
    if reported is None or reported != requested:
        raise DataIntegrityError(message, details={"requested_cik": requested, "field": "cik"})
    return requested
