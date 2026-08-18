"""Parse SEC companyfacts JSON into FactRecord models."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import DataIntegrityError, ProviderError
from financial_analyst_agent.domain.models import FactRecord
from financial_analyst_agent.providers.sec.identity import (
    require_matching_payload_cik,
    require_requested_cik,
)
from financial_analyst_agent.services.metric_catalog import get_concept_candidates


def require_companyfacts_object(raw: object, cik: str) -> dict[str, Any]:
    """
    Validate that a decoded companyfacts response is a JSON object.

    The root shape is part of issuer identity for this endpoint: an array, scalar, or
    null root cannot carry a CIK, so it can never be attributed to the requested
    issuer. It is therefore an integrity violation, not issuer unavailability.
    """
    requested = require_requested_cik(cik)
    if not isinstance(raw, dict):
        raise DataIntegrityError(
            "companyfacts response root is not an object and cannot report a CIK",
            details={"requested_cik": requested, "field": "root"},
        )
    return raw


def require_matching_companyfacts_cik(payload: dict[str, Any], cik: str) -> dict[str, Any]:
    """Validate that a companyfacts payload reports the requested issuer CIK."""
    require_matching_payload_cik(
        payload,
        cik,
        message="companyfacts response identity does not match the requested CIK",
    )
    return payload


def require_companyfacts_structure(
    payload: dict[str, Any],
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the companyfacts container. Structure problems are availability failures."""
    error_details = details or {}
    if "facts" not in payload:
        raise ProviderError("companyfacts response missing facts", details=error_details)
    if not isinstance(payload["facts"], dict):
        raise ProviderError("companyfacts response facts must be an object", details=error_details)
    return payload


def validate_companyfacts_payload(
    payload: dict[str, Any],
    cik: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validated-retrieval boundary for companyfacts: identity first, then structure.

    Ordering matters. A payload that claims another issuer *and* is malformed is an
    integrity violation, so it must never be reported as issuer unavailability.
    """
    require_matching_companyfacts_cik(payload, cik)
    return require_companyfacts_structure(payload, details=details)


def validate_companyfacts_response(
    raw: object,
    cik: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validate decoded companyfacts JSON: root object, then identity, then structure.

    This is the single entry point used for live and cached responses alike, so both
    receive the same classification.
    """
    payload = require_companyfacts_object(raw, cik)
    return validate_companyfacts_payload(payload, cik, details=details)


def parse_company_facts(
    payload: dict[str, Any],
    metric: Metric,
    unit: str,
) -> tuple[list[FactRecord], list[dict[str, Any]]]:
    """Parse FactRecords for supported metric concepts and unit."""
    return parse_company_facts_for_concepts(payload, get_concept_candidates(metric), unit)


def parse_company_facts_for_concepts(
    payload: dict[str, Any],
    concepts: list[tuple[str, str]],
    unit: str,
) -> tuple[list[FactRecord], list[dict[str, Any]]]:
    """
    Parse FactRecords for explicit (taxonomy, concept) candidates and unit.

    Returns parsed records and per-record rejection diagnostics.
    """
    facts_root = payload.get("facts")
    if not isinstance(facts_root, dict):
        raise ProviderError("companyfacts payload missing facts object")

    records: list[FactRecord] = []
    rejections: list[dict[str, Any]] = []

    for taxonomy, concept in concepts:
        taxonomy_facts = facts_root.get(taxonomy)
        if taxonomy_facts is None:
            continue
        if not isinstance(taxonomy_facts, dict):
            raise ProviderError(
                f"taxonomy '{taxonomy}' must be an object",
                details={"taxonomy": taxonomy},
            )

        concept_facts = taxonomy_facts.get(concept)
        if concept_facts is None:
            continue
        if not isinstance(concept_facts, dict):
            raise ProviderError(
                f"concept '{taxonomy}/{concept}' must be an object",
                details={"taxonomy": taxonomy, "concept": concept},
            )

        units = concept_facts.get("units")
        if units is None:
            continue
        if not isinstance(units, dict):
            raise ProviderError(
                f"units for '{taxonomy}/{concept}' must be an object",
                details={"taxonomy": taxonomy, "concept": concept},
            )

        unit_facts = units.get(unit)
        if unit_facts is None:
            continue
        if not isinstance(unit_facts, list):
            raise ProviderError(
                f"unit '{unit}' for '{taxonomy}/{concept}' must be a list",
                details={"taxonomy": taxonomy, "concept": concept, "unit": unit},
            )

        for index, raw_fact in enumerate(unit_facts):
            if not isinstance(raw_fact, dict):
                rejections.append(
                    {
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "index": index,
                        "reason": "fact is not an object",
                    }
                )
                continue
            try:
                records.append(_parse_fact_record(raw_fact, taxonomy, concept, unit))
            except ValueError as exc:
                rejections.append(
                    {
                        "taxonomy": taxonomy,
                        "concept": concept,
                        "index": index,
                        "reason": str(exc),
                    }
                )
    return records, rejections


def _parse_fact_record(
    raw_fact: dict[str, Any],
    taxonomy: str,
    concept: str,
    unit: str,
) -> FactRecord:
    end_raw = raw_fact.get("end")
    if not isinstance(end_raw, str):
        raise ValueError("missing or invalid end date")
    end_date = date.fromisoformat(end_raw)

    start_date: date | None = None
    if "start" in raw_fact:
        start_raw = raw_fact.get("start")
        if start_raw is None:
            start_date = None
        elif isinstance(start_raw, str):
            start_date = date.fromisoformat(start_raw)
        else:
            raise ValueError("invalid start date")

    accession_number = raw_fact.get("accn")
    if not isinstance(accession_number, str):
        raise ValueError("missing or invalid accession number")

    form = raw_fact.get("form")
    if not isinstance(form, str):
        raise ValueError("missing or invalid form")

    filed_raw = raw_fact.get("filed")
    if not isinstance(filed_raw, str):
        raise ValueError("missing or invalid filed date")
    filed_date = date.fromisoformat(filed_raw)

    value = _parse_sec_monetary_value(raw_fact.get("val"))

    return FactRecord(
        accession_number=accession_number,
        end_date=end_date,
        start_date=start_date,
        form=form,
        unit=unit,
        value=value,
        concept=concept,
        taxonomy=taxonomy,
        filed_date=filed_date,
    )


def _parse_sec_monetary_value(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("monetary value cannot be boolean")
    if isinstance(value, float):
        raise ValueError("monetary JSON float values are unsupported")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise ValueError("invalid monetary string value") from None
    raise ValueError(f"unsupported monetary value type: {type(value).__name__}")
