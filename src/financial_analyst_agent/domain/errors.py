"""Typed exception hierarchy."""

from typing import Any


class FinancialAnalystError(Exception):
    """Base exception for all domain errors."""

    code: str = "financial_analyst_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnsupportedQuarterlyFactError(FinancialAnalystError):
    code = "unsupported_quarterly_fact"


class PerShareNotDerivableError(UnsupportedQuarterlyFactError):
    """A per-share figure the filings report only for a longer period (ADR 0007)."""

    code = "not_reported_for_quarter"


class AmbiguousFactError(FinancialAnalystError):
    code = "ambiguous_fact"


class FilingNotFoundError(FinancialAnalystError):
    code = "filing_not_found"


class UnknownMetricError(FinancialAnalystError):
    code = "unknown_metric"


class ProviderError(FinancialAnalystError):
    """A data or model provider failed. Its message is for the log, not the visitor."""

    code = "provider_error"


class ProviderRefusal(ProviderError):
    """A provider's answer written for the visitor ("The recorded demo replays written
    answers only for…"), shown as it is."""

    code = "provider_refusal"


class DataIntegrityError(FinancialAnalystError):
    """A trusted source violated an identity or invariant guarantee."""

    code = "data_integrity_error"


class CompanyNotFoundError(FinancialAnalystError):
    code = "company_not_found"


class IneligibleIssuerError(CompanyNotFoundError):
    """A listing that is not an operating company: a fund, BDC, SPAC or note (ADR 0002)."""

    code = "ineligible_issuer"


class AmbiguousCompanyError(FinancialAnalystError):
    code = "ambiguous_company"


class InvalidParameterError(FinancialAnalystError):
    code = "invalid_parameter"


class ConfigurationError(FinancialAnalystError):
    """Invalid, incomplete, or contradictory application configuration."""

    code = "configuration_error"


class UnknownIndustryError(FinancialAnalystError):
    code = "unknown_industry"


class PlannerError(FinancialAnalystError):
    code = "planner_error"


class SessionQuotaError(FinancialAnalystError):
    code = "session_quota"


class RuntimeMismatchError(FinancialAnalystError):
    """A turn asked to run on a thread bound to the other runtime."""

    code = "runtime_mismatch"


# A source that failed, as opposed to data that lacks the fact: the fact may well exist.
SOURCE_FAILURES = (ProviderError, DataIntegrityError, OSError)
