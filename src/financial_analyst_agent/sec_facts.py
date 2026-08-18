"""Live SEC fact lookup: identity plus companyfacts selection."""

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.providers.sec.company_facts import parse_company_facts
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.providers.sec.submissions import parse_submissions
from financial_analyst_agent.providers.sec.urls import build_filing_source_url
from financial_analyst_agent.services.fact_selector import (
    select_quarterly_fact_with_filing_fallback,
)
from financial_analyst_agent.services.metric_catalog import parse_metric

_SUPPORTED_CURRENCY = "USD"


class SecFactLookup:
    """Live EDGAR lookup behind the same get_financials port as the fixture adapter."""

    def __init__(self, settings: Settings, client: SECClient | None = None) -> None:
        self._client = client or SECClient(settings)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_financials(self, company: str, metric: str) -> FinancialFact:
        parsed_metric = parse_metric(metric)
        tickers_payload = self._client.get_company_tickers()
        resolved = resolve_company(company, tickers_payload)
        ticker = resolved.tickers[0] if resolved.tickers else company.upper()
        submissions_payload = self._client.get_submissions(resolved.cik)
        filings = parse_submissions(submissions_payload)
        company_facts_payload = self._client.get_company_facts(resolved.cik)
        records, _rejections = parse_company_facts(
            company_facts_payload,
            parsed_metric,
            _SUPPORTED_CURRENCY,
        )
        return select_quarterly_fact_with_filing_fallback(
            records,
            filings,
            parsed_metric,
            _SUPPORTED_CURRENCY,
            resolved.name,
            ticker,
            resolved.cik,
            lambda filing: build_filing_source_url(resolved.cik, filing),
        )
