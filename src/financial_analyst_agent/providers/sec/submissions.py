"""Parse SEC submissions JSON into Filing models."""

import re
from datetime import date
from typing import Any

from financial_analyst_agent.domain.enums import FormType
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.domain.models import Filing
from financial_analyst_agent.providers.sec.identity import require_matching_payload_cik

_ACCESSION_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_QUARTERLY_FORMS = frozenset({FormType.FORM_10_Q, FormType.FORM_10_Q_A})


def require_matching_submissions_cik(payload: dict[str, Any], cik: str) -> dict[str, Any]:
    """Validate that a submissions payload reports the requested issuer CIK."""
    require_matching_payload_cik(
        payload,
        cik,
        message="submissions response identity does not match the requested CIK",
    )
    return payload


def require_submissions_structure(
    payload: dict[str, Any],
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the submissions container. Structure problems are availability failures."""
    error_details = details or {}
    if "filings" not in payload:
        raise ProviderError("submissions response missing filings", details=error_details)
    if not isinstance(payload["filings"], dict):
        raise ProviderError("submissions response filings must be an object", details=error_details)
    return payload


def validate_submissions_response(
    payload: dict[str, Any],
    cik: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validated-retrieval boundary for submissions: identity first, then structure.

    Ordering matters. A response describing another issuer is an integrity violation
    even when its filing arrays are also malformed, so it must never be reported as
    issuer unavailability or converted into a partial item failure.
    """
    require_matching_submissions_cik(payload, cik)
    return require_submissions_structure(payload, details=details)


def parse_submissions(payload: dict[str, Any]) -> list[Filing]:
    """Parse quarterly filings from a SEC submissions response."""
    filings_section = payload.get("filings")
    if not isinstance(filings_section, dict):
        raise ProviderError("submissions payload missing filings object")

    recent = filings_section.get("recent")
    if not isinstance(recent, dict):
        raise ProviderError("submissions payload missing filings.recent object")

    forms = recent.get("form")
    if not isinstance(forms, list):
        raise ProviderError("submissions recent.form must be a list")

    expected_length = len(forms)
    accession_numbers = _require_recent_list(recent, "accessionNumber", expected_length)
    filing_dates = _require_recent_list(recent, "filingDate", expected_length)
    report_dates = _require_recent_list(recent, "reportDate", expected_length)
    primary_documents = _require_recent_list(recent, "primaryDocument", expected_length)

    filings: list[Filing] = []
    for index, raw_form in enumerate(forms):
        # Every provider-supplied field is type-checked before use, so malformed data
        # raises the sanitized provider boundary error instead of a built-in TypeError.
        form = _require_provider_string(raw_form, "form", index)
        if form not in _QUARTERLY_FORMS:
            continue
        accession_number = _require_provider_string(
            accession_numbers[index], "accessionNumber", index
        )
        if not _ACCESSION_PATTERN.match(accession_number):
            continue
        filed_date = _parse_iso_date(filing_dates[index], "filingDate", index)
        report_date = _parse_iso_date(report_dates[index], "reportDate", index)
        primary_document = _require_optional_provider_string(
            primary_documents[index], "primaryDocument", index
        )
        filings.append(
            Filing(
                form=form,
                accession_number=accession_number,
                filed_date=filed_date,
                report_date=report_date,
                primary_document=primary_document,
            )
        )
    return filings


def _require_recent_list(
    recent: dict[str, Any],
    field_name: str,
    expected_length: int,
) -> list[Any]:
    values = recent.get(field_name)
    if not isinstance(values, list):
        raise ProviderError(f"submissions recent.{field_name} must be a list")
    if len(values) != expected_length:
        raise ProviderError(
            f"submissions recent.{field_name} length mismatch",
            details={"field": field_name, "expected": expected_length, "actual": len(values)},
        )
    return values


def _require_provider_string(value: object, field_name: str, index: int) -> str:
    """Require an exact string. ``bool`` and numbers are rejected, never coerced."""
    if not isinstance(value, str):
        raise ProviderError(
            f"submissions recent.{field_name} must be a string",
            details={"field": field_name, "index": index, "value_type": type(value).__name__},
        )
    return value


def _require_optional_provider_string(value: object, field_name: str, index: int) -> str | None:
    if value is None:
        return None
    return _require_provider_string(value, field_name, index)


def _parse_iso_date(value: object, field_name: str, index: int) -> date:
    text = _require_provider_string(value, field_name, index)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        # Raw provider values never enter client-facing details.
        raise ProviderError(
            f"invalid ISO date for {field_name} at index {index}",
            details={"field": field_name, "index": index},
        ) from exc
