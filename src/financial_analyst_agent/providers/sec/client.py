"""Synchronous SEC EDGAR HTTP client."""

import json
import time
from typing import Any

import httpx

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.observability import call_provider
from financial_analyst_agent.providers.sec.company_facts import validate_companyfacts_response
from financial_analyst_agent.providers.sec.submissions import validate_submissions_response
from financial_analyst_agent.providers.sec.tickers import require_usable_company_tickers

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY_SECONDS = 1.0
_MAX_RETRY_DELAY_SECONDS = 5.0


class SECClient:
    """HTTP client for SEC EDGAR JSON APIs with rate limiting and retry."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._user_agent = settings.require_user_agent()
        self._timeout = settings.sec_timeout_seconds
        self._owns_client = client is None
        self._client = client
        self._min_interval = 1.0 / settings.sec_max_requests_per_second
        self._last_request_at = 0.0
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def _acquire(self) -> None:
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _fetch_json(self, url: str) -> object:
        def _run() -> object:
            last_error: Exception | None = None
            for attempt in range(_MAX_RETRIES):
                self._acquire()
                try:
                    return self._fetch_json_once(url)
                except ProviderError as exc:
                    last_error = exc
                    if not exc.details.get("retryable") or attempt + 1 >= _MAX_RETRIES:
                        raise
                    delay = min(
                        _DEFAULT_RETRY_DELAY_SECONDS * (attempt + 1),
                        _MAX_RETRY_DELAY_SECONDS,
                    )
                    time.sleep(delay)
            if last_error is not None:
                raise last_error
            raise ProviderError("SEC request failed after retries", details={"url": url})

        return call_provider("sec", _run, url=url)

    def _fetch_json_once(self, url: str) -> object:
        headers = {
            "User-Agent": self._user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }
        try:
            response = self._http().get(url, headers=headers, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "SEC request timed out",
                details={"url": url, "retryable": True},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "SEC request failed",
                details={"url": url, "retryable": True},
            ) from exc

        status = response.status_code
        if status == 429 or 500 <= status <= 599:
            raise ProviderError(
                "SEC rate limit exceeded" if status == 429 else "SEC server error",
                details={"url": url, "status_code": status, "retryable": True},
            )
        if 400 <= status <= 499:
            raise ProviderError(
                "SEC client error",
                details={"url": url, "status_code": status, "retryable": False},
            )
        if status < 200 or status >= 300:
            raise ProviderError(
                "Unexpected SEC response status",
                details={"url": url, "status_code": status, "retryable": False},
            )
        try:
            decoded: object = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "SEC response was not valid JSON",
                details={"url": url, "retryable": False},
            ) from exc
        return decoded

    def _fetch_body(self, url: str) -> str:
        def _run() -> str:
            last_error: Exception | None = None
            for attempt in range(_MAX_RETRIES):
                self._acquire()
                try:
                    return self._fetch_body_once(url)
                except ProviderError as exc:
                    last_error = exc
                    if not exc.details.get("retryable") or attempt + 1 >= _MAX_RETRIES:
                        raise
                    delay = min(
                        _DEFAULT_RETRY_DELAY_SECONDS * (attempt + 1),
                        _MAX_RETRY_DELAY_SECONDS,
                    )
                    time.sleep(delay)
            if last_error is not None:
                raise last_error
            raise ProviderError("SEC request failed after retries", details={"url": url})

        return call_provider("sec", _run, url=url)

    def _fetch_body_once(self, url: str) -> str:
        headers = {
            "User-Agent": self._user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "text/html,application/xhtml+xml,application/json",
        }
        try:
            response = self._http().get(url, headers=headers, timeout=self._timeout)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "SEC request timed out",
                details={"url": url, "retryable": True},
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "SEC request failed",
                details={"url": url, "retryable": True},
            ) from exc
        status = response.status_code
        if status == 429 or 500 <= status <= 599:
            raise ProviderError(
                "SEC rate limit exceeded" if status == 429 else "SEC server error",
                details={"url": url, "status_code": status, "retryable": True},
            )
        if 400 <= status <= 499:
            raise ProviderError(
                "SEC client error",
                details={"url": url, "status_code": status, "retryable": False},
            )
        if status < 200 or status >= 300:
            raise ProviderError(
                "Unexpected SEC response status",
                details={"url": url, "status_code": status, "retryable": False},
            )
        return response.text

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        from financial_analyst_agent.providers.sec.urls import build_filing_document_url

        return self._fetch_body(build_filing_document_url(cik, accession, document))

    def get_company_tickers(self) -> dict[str, Any]:
        return require_usable_company_tickers(self._fetch_json(_COMPANY_TICKERS_URL))

    def get_submissions(self, cik: str) -> dict[str, Any]:
        url = f"{self._settings.sec_base_url}/submissions/CIK{cik}.json"
        payload = self._fetch_json(url)
        if not isinstance(payload, dict):
            raise ProviderError(
                "SEC response JSON must be an object",
                details={"url": url, "retryable": False},
            )
        return validate_submissions_response(payload, cik, details={"url": url, "cik": cik})

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        url = f"{self._settings.sec_base_url}/api/xbrl/companyfacts/CIK{cik}.json"
        return validate_companyfacts_response(
            self._fetch_json(url), cik, details={"url": url, "cik": cik}
        )
