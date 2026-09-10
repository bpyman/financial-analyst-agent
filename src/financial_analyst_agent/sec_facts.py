"""SEC fact lookup over an injectable live or recorded data source."""

from datetime import date
from typing import Any, Protocol

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


class SECDataSource(Protocol):
    """Provider boundary shared by live EDGAR and offline recordings."""

    def get_company_tickers(self) -> dict[str, Any]: ...

    def get_submissions(self, cik: str) -> dict[str, Any]: ...

    def get_company_facts(self, cik: str) -> dict[str, Any]: ...

    def close(self) -> None: ...


def _related_lookup_ciks(
    resolved_cik: str,
    filings: list[Filing],
    *,
    report_date: date | None = None,
) -> tuple[str, ...]:
    """Ticker-map CIK first, then a distinct accession-prefix filer if present."""
    ordered = [resolved_cik]
    try:
        candidates = get_candidate_filings(filings, report_date=report_date)
    except FilingNotFoundError:
        return tuple(ordered)
    for filing in candidates:
        related = parse_cik(filing.accession_number.split("-", 1)[0])
        if related is not None and related not in ordered:
            ordered.append(related)
    return tuple(ordered)


class SecFactLookup:
    """SEC XBRL lookup behind the application's get_financials port."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: SECDataSource | None = None,
    ) -> None:
        self._tickers: dict[str, Any] | None = None
        self._submissions_by_cik: dict[str, dict[str, Any]] = {}
        self._company_facts_by_cik: dict[str, dict[str, Any] | None] = {}
        if client is not None:
            self._client: SECDataSource = client
            self._owns_client = False
            return
        if settings is None:
            raise TypeError("settings are required when no SEC data source is provided")
        self._client = SECClient(settings)
        self._owns_client = True

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _cached_company_tickers(self) -> dict[str, Any]:
        if self._tickers is None:
            self._tickers = self._client.get_company_tickers()
        return self._tickers

    def _cached_submissions(self, cik: str) -> dict[str, Any]:
        payload = self._submissions_by_cik.get(cik)
        if payload is None:
            payload = self._client.get_submissions(cik)
            self._submissions_by_cik[cik] = payload
        return payload

    def _cached_company_facts(self, cik: str) -> dict[str, Any]:
        if cik in self._company_facts_by_cik:
            payload = self._company_facts_by_cik[cik]
            if payload is None:
                raise ProviderError(
                    "No SEC companyfacts response exists for the issuer",
                    details={"cik": cik, "status_code": 404},
                )
            return payload
        try:
            payload = self._client.get_company_facts(cik)
        except ProviderError as exc:
            if exc.details.get("status_code") == 404:
                self._company_facts_by_cik[cik] = None
            raise
        self._company_facts_by_cik[cik] = payload
        return payload

    def get_financials(
        self,
        company: str,
        metric: str,
        *,
        report_date: date | None = None,
    ) -> FinancialFact:
        parsed_metric = parse_metric(metric)
        tickers_payload = self._cached_company_tickers()
        resolved = resolve_company(company, tickers_payload)
        ticker = resolved.tickers[0] if resolved.tickers else company.upper()
        submissions_payload = self._cached_submissions(resolved.cik)
        filings = parse_submissions(submissions_payload)
        last_unsupported: UnsupportedQuarterlyFactError | FilingNotFoundError | None = None
        last_missing: ProviderError | None = None
        for cik in _related_lookup_ciks(resolved.cik, filings, report_date=report_date):
            try:
                company_facts_payload = self._cached_company_facts(cik)
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
                selected = select_quarterly_fact_with_filing_fallback(
                    records,
                    filings,
                    parsed_metric,
                    _SUPPORTED_CURRENCY,
                    resolved.name,
                    ticker,
                    cik,
                    source_url_for_filing,
                    report_date=report_date,
                )
            except (UnsupportedQuarterlyFactError, FilingNotFoundError) as exc:
                last_unsupported = exc
                continue
            return selected[0]
        if isinstance(last_unsupported, FilingNotFoundError):
            raise UnsupportedQuarterlyFactError(
                str(last_unsupported),
                details=last_unsupported.details,
            ) from last_unsupported
        if last_unsupported is not None:
            raise last_unsupported
        if last_missing is not None:
            raise UnsupportedQuarterlyFactError(
                "No SEC companyfacts response exists for the issuer",
                details={"metric": parsed_metric.value},
            ) from last_missing
        raise UnsupportedQuarterlyFactError(
            "No directly reported standalone-quarter fact exists for metric",
            details={"metric": parsed_metric.value},
        )

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        """Newest-first distinct quarterly report dates for a company."""
        from financial_analyst_agent.services.filing_selector import list_quarterly_report_dates

        tickers_payload = self._cached_company_tickers()
        resolved = resolve_company(company, tickers_payload)
        submissions_payload = self._cached_submissions(resolved.cik)
        filings = parse_submissions(submissions_payload)
        return tuple(list_quarterly_report_dates(filings, limit=limit))

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        getter = getattr(self._client, "get_filing_document", None)
        if not callable(getter):
            raise ProviderError("Filing documents are not available on this SEC source")
        return str(getter(cik, accession, document))
