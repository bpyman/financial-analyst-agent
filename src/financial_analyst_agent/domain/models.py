"""Domain models."""

from datetime import date

from pydantic import BaseModel, Field

from financial_analyst_agent.domain.enums import DataSourceKind, Metric
from financial_analyst_agent.domain.serialization import DecimalStr


class Company(BaseModel):
    """Resolved SEC-reporting company."""

    cik: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    name: str
    tickers: list[str] = Field(default_factory=list)


class Filing(BaseModel):
    """SEC filing metadata for a reporting period."""

    form: str
    accession_number: str
    filed_date: date
    report_date: date
    primary_document: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None


class FactRecord(BaseModel):
    """Normalized XBRL fact used as input to the deterministic selector."""

    accession_number: str
    end_date: date
    start_date: date | None = None
    form: str
    unit: str
    value: DecimalStr
    concept: str
    taxonomy: str
    filed_date: date


class DerivationPart(BaseModel):
    """One directly reported fact a derived quarter was computed from."""

    value: DecimalStr
    start_date: date
    end_date: date
    form: str
    accession_number: str
    taxonomy: str
    concept: str
    filed_date: date
    source_url: str


class Derivation(BaseModel):
    """How a derived quarter was computed: ``parts[0]`` minus ``parts[1]`` (ADR 0007)."""

    method: str
    label: str
    parts: list[DerivationPart]


class FinancialFact(BaseModel):
    """A quarterly financial fact with typed provenance."""

    company_name: str
    ticker: str
    cik: str = Field(min_length=10, max_length=10, pattern=r"^\d{10}$")
    metric: Metric
    value: DecimalStr
    currency: str
    start_date: date
    end_date: date
    filed_date: date
    form: str
    accession_number: str
    taxonomy: str
    concept: str
    source_url: str
    directly_reported: bool = True
    derivation: Derivation | None = None
    source: DataSourceKind = DataSourceKind.SEC_XBRL
