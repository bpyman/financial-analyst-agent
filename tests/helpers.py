"""Shared test helpers."""

from datetime import date
from decimal import Decimal

from financial_analyst_agent.domain.models import FactRecord, Filing


def make_filing(
    *,
    form: str = "10-Q",
    accession_number: str = "0000320193-24-000081",
    filed_date: date = date(2024, 11, 1),
    report_date: date = date(2024, 9, 28),
    primary_document: str | None = "aapl-20240928.htm",
) -> Filing:
    return Filing(
        form=form,
        accession_number=accession_number,
        filed_date=filed_date,
        report_date=report_date,
        primary_document=primary_document,
        fiscal_year=2024,
        fiscal_period="Q3",
    )


def make_fact(
    *,
    accession_number: str = "0000320193-24-000081",
    end_date: date = date(2024, 9, 28),
    start_date: date | None = date(2024, 6, 30),
    form: str = "10-Q",
    unit: str = "USD",
    value: Decimal = Decimal("23636000000"),
    concept: str = "NetIncomeLoss",
    taxonomy: str = "us-gaap",
    filed_date: date = date(2024, 11, 1),
) -> FactRecord:
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
