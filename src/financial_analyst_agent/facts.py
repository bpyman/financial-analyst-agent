"""Fixture-runtime fact lookup: identity plus recorded XBRL selection."""

from datetime import date
from decimal import Decimal

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import CompanyNotFoundError
from financial_analyst_agent.domain.models import FactRecord, Filing, FinancialFact
from financial_analyst_agent.providers.sec.aliases import ALIASES
from financial_analyst_agent.services.fact_selector import select_quarterly_fact

_ALPHABET_NAME = "Alphabet Inc."
_ALPHABET_CIK = "0001652044"
_ALPHABET_TICKER = "GOOG"

_FILING = Filing(
    form="10-Q",
    accession_number="0001652044-26-000071",
    filed_date=date(2026, 7, 23),
    report_date=date(2026, 6, 30),
    primary_document="goog-20260630.htm",
)
_SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/1652044/"
    "000165204426000071/goog-20260630.htm"
)


def _record(*, start_date: date, value: Decimal) -> FactRecord:
    return FactRecord(
        accession_number=_FILING.accession_number,
        end_date=_FILING.report_date,
        start_date=start_date,
        form=_FILING.form,
        unit="USD",
        value=value,
        concept="NetIncomeLoss",
        taxonomy="us-gaap",
        filed_date=_FILING.filed_date,
    )


# YTD duration is a distractor; selector must keep the standalone quarter.
_RECORDED_FACTS = [
    _record(start_date=date(2026, 1, 1), value=Decimal("50000000000")),
    _record(start_date=date(2026, 4, 1), value=Decimal("20000000000")),
]


class FixtureFactLookup:
    """Recorded Alphabet facts. Never calls live SEC."""

    def get_financials(self, company: str, metric: str) -> FinancialFact:
        issuer_name, ticker, cik = _resolve_issuer(company)
        return select_quarterly_fact(
            _RECORDED_FACTS,
            _FILING,
            Metric(metric),
            "USD",
            company_name=issuer_name,
            ticker=ticker,
            cik=cik,
            source_url=_SOURCE_URL,
        )


def _resolve_issuer(query: str) -> tuple[str, str, str]:
    normalized = query.strip().casefold()
    legal_name = ALIASES.get(normalized, query.strip())
    if legal_name.casefold() == _ALPHABET_NAME.casefold() or normalized in {
        "goog",
        "googl",
        _ALPHABET_CIK,
    }:
        return _ALPHABET_NAME, _ALPHABET_TICKER, _ALPHABET_CIK
    raise CompanyNotFoundError(f"Unknown issuer: {query}")
