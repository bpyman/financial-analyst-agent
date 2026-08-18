"""Fixture-runtime fact lookup: identity plus recorded XBRL selection."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import CompanyNotFoundError
from financial_analyst_agent.domain.models import FactRecord, Filing, FinancialFact
from financial_analyst_agent.providers.sec.aliases import ALIASES
from financial_analyst_agent.services.fact_selector import select_quarterly_fact

_QUARTER_START = date(2026, 4, 1)
_QUARTER_END = date(2026, 6, 30)
_YTD_START = date(2026, 1, 1)


@dataclass(frozen=True)
class _IssuerFixture:
    name: str
    ticker: str
    cik: str
    filing: Filing
    source_url: str
    facts: tuple[FactRecord, ...]


def _record(filing: Filing, *, start_date: date, value: Decimal, concept: str) -> FactRecord:
    return FactRecord(
        accession_number=filing.accession_number,
        end_date=filing.report_date,
        start_date=start_date,
        form=filing.form,
        unit="USD",
        value=value,
        concept=concept,
        taxonomy="us-gaap",
        filed_date=filing.filed_date,
    )


_ALPHABET_FILING = Filing(
    form="10-Q",
    accession_number="0001652044-26-000071",
    filed_date=date(2026, 7, 23),
    report_date=_QUARTER_END,
    primary_document="goog-20260630.htm",
)
_ALPHABET = _IssuerFixture(
    name="Alphabet Inc.",
    ticker="GOOG",
    cik="0001652044",
    filing=_ALPHABET_FILING,
    source_url=(
        "https://www.sec.gov/Archives/edgar/data/1652044/"
        "000165204426000071/goog-20260630.htm"
    ),
    facts=(
        # YTD duration is a distractor; selector must keep the standalone quarter.
        _record(
            _ALPHABET_FILING,
            start_date=_YTD_START,
            value=Decimal("50000000000"),
            concept="NetIncomeLoss",
        ),
        _record(
            _ALPHABET_FILING,
            start_date=_QUARTER_START,
            value=Decimal("20000000000"),
            concept="NetIncomeLoss",
        ),
        _record(
            _ALPHABET_FILING,
            start_date=_QUARTER_START,
            value=Decimal("28000000000"),
            concept="OperatingIncomeLoss",
        ),
        _record(
            _ALPHABET_FILING,
            start_date=_QUARTER_START,
            value=Decimal("80000000000"),
            concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        ),
    ),
)

_MICROSOFT_FILING = Filing(
    form="10-Q",
    accession_number="0000789019-26-000088",
    filed_date=date(2026, 7, 22),
    report_date=_QUARTER_END,
    primary_document="msft-20260630.htm",
)
_MICROSOFT = _IssuerFixture(
    name="Microsoft Corporation",
    ticker="MSFT",
    cik="0000789019",
    filing=_MICROSOFT_FILING,
    source_url=(
        "https://www.sec.gov/Archives/edgar/data/789019/"
        "000078901926000088/msft-20260630.htm"
    ),
    facts=(
        _record(
            _MICROSOFT_FILING,
            start_date=_QUARTER_START,
            value=Decimal("32000000000"),
            concept="OperatingIncomeLoss",
        ),
        _record(
            _MICROSOFT_FILING,
            start_date=_QUARTER_START,
            value=Decimal("64000000000"),
            concept="Revenues",
        ),
    ),
)

_LILLY_FILING = Filing(
    form="10-Q",
    accession_number="0000059478-26-000040",
    filed_date=date(2026, 7, 21),
    report_date=_QUARTER_END,
    primary_document="lly-20260630.htm",
)
_LILLY = _IssuerFixture(
    name="Eli Lilly and Company",
    ticker="LLY",
    cik="0000059478",
    filing=_LILLY_FILING,
    source_url=(
        "https://www.sec.gov/Archives/edgar/data/59478/"
        "000005947826000040/lly-20260630.htm"
    ),
    facts=(
        _record(
            _LILLY_FILING,
            start_date=_QUARTER_START,
            value=Decimal("2800000000"),
            concept="NetIncomeLoss",
        ),
    ),
)

_UNITEDHEALTH_FILING = Filing(
    form="10-Q",
    accession_number="0000731766-26-000055",
    filed_date=date(2026, 7, 20),
    report_date=_QUARTER_END,
    primary_document="unh-20260630.htm",
)
_UNITEDHEALTH = _IssuerFixture(
    name="UnitedHealth Group Incorporated",
    ticker="UNH",
    cik="0000731766",
    filing=_UNITEDHEALTH_FILING,
    source_url=(
        "https://www.sec.gov/Archives/edgar/data/731766/"
        "000073176626000055/unh-20260630.htm"
    ),
    facts=(
        _record(
            _UNITEDHEALTH_FILING,
            start_date=_QUARTER_START,
            value=Decimal("4200000000"),
            concept="NetIncomeLoss",
        ),
    ),
)

_ISSUERS: tuple[_IssuerFixture, ...] = (_ALPHABET, _MICROSOFT, _LILLY, _UNITEDHEALTH)


class FixtureFactLookup:
    """Recorded issuer facts. Never calls live SEC."""

    def get_financials(self, company: str, metric: str) -> tuple[FinancialFact, ...]:
        issuer = _resolve_issuer(company)
        return select_quarterly_fact(
            list(issuer.facts),
            issuer.filing,
            Metric(metric),
            "USD",
            company_name=issuer.name,
            ticker=issuer.ticker,
            cik=issuer.cik,
            source_url=issuer.source_url,
        )


def _resolve_issuer(query: str) -> _IssuerFixture:
    normalized = query.strip().casefold()
    legal_name = ALIASES.get(normalized, query.strip())
    for issuer in _ISSUERS:
        aliases = {
            issuer.name.casefold(),
            issuer.ticker.casefold(),
            issuer.cik,
        }
        if issuer is _ALPHABET:
            aliases.update({"goog", "googl", "google", "alphabet"})
        if issuer is _MICROSOFT:
            aliases.update({"microsoft", "msft"})
        if normalized in aliases or legal_name.casefold() == issuer.name.casefold():
            return issuer
    raise CompanyNotFoundError(f"Unknown issuer: {query}")
