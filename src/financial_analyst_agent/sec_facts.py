"""Live SEC fact lookup: identity plus companyfacts selection."""

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import (
    FilingNotFoundError,
    ProviderError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import Filing, FinancialFact
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.providers.sec.company_facts import parse_company_facts
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.providers.sec.submissions import parse_submissions
from financial_analyst_agent.providers.sec.tickers import parse_cik
from financial_analyst_agent.providers.sec.urls import build_filing_source_url
from financial_analyst_agent.services.fact_selector import (
    select_quarterly_fact_with_filing_fallback,
)
from financial_analyst_agent.services.filing_selector import get_candidate_filings
from financial_analyst_agent.services.metric_catalog import parse_metric

_SUPPORTED_CURRENCY = "USD"


def related_lookup_ciks(resolved_cik: str, filings: list[Filing]) -> tuple[str, ...]:
    """Ticker-map CIK first, then a distinct accession-prefix filer if present."""
    ordered = [resolved_cik]
    try:
        candidates = get_candidate_filings(filings)
    except FilingNotFoundError:
        return tuple(ordered)
    for filing in candidates:
        related = parse_cik(filing.accession_number.split("-", 1)[0])
        if related is not None and related not in ordered:
            ordered.append(related)
    return tuple(ordered)


class SecFactLookup:
    """Live EDGAR lookup behind the same get_financials port as the fixture adapter."""

    def __init__(self, settings: Settings, client: SECClient | None = None) -> None:
        self._client = client or SECClient(settings)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_financials(self, company: str, metric: str) -> tuple[FinancialFact, ...]:
        parsed_metric = parse_metric(metric)
        tickers_payload = self._client.get_company_tickers()
        resolved = resolve_company(company, tickers_payload)
        ticker = resolved.tickers[0] if resolved.tickers else company.upper()
        submissions_payload = self._client.get_submissions(resolved.cik)
        filings = parse_submissions(submissions_payload)
        last_unsupported: UnsupportedQuarterlyFactError | FilingNotFoundError | None = None
        last_missing: ProviderError | None = None
        for cik in related_lookup_ciks(resolved.cik, filings):
            try:
                company_facts_payload = self._client.get_company_facts(cik)
            except ProviderError as exc:
                if exc.details.get("status_code") != 404:
                    raise
                last_missing = exc
                continue
            records, _rejections = parse_company_facts(
                company_facts_payload,
                parsed_metric,
                _SUPPORTED_CURRENCY,
            )
            def source_url_for_filing(filing: Filing, issuer_cik: str = cik) -> str:
                return build_filing_source_url(issuer_cik, filing)

            try:
                return select_quarterly_fact_with_filing_fallback(
                    records,
                    filings,
                    parsed_metric,
                    _SUPPORTED_CURRENCY,
                    resolved.name,
                    ticker,
                    cik,
                    source_url_for_filing,
                )
            except (UnsupportedQuarterlyFactError, FilingNotFoundError) as exc:
                last_unsupported = exc
        if last_unsupported is not None:
            raise last_unsupported
        if last_missing is not None:
            raise last_missing
        raise UnsupportedQuarterlyFactError(
            "No directly reported standalone-quarter fact exists for metric",
            details={"metric": parsed_metric.value},
        )
