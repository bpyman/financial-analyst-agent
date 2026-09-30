"""Synchronous SEC EDGAR HTTP client."""

import json
import re
import threading
import time
from datetime import date
from typing import Any

import httpx

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.observability import call_provider
from financial_analyst_agent.providers.sec.company_facts import validate_companyfacts_response
from financial_analyst_agent.providers.sec.submissions import validate_submissions_response
from financial_analyst_agent.providers.sec.tickers import require_usable_company_tickers

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
# SEC's "recent" filings hold the last year or 1,000 filings, whichever is more.
# A bank filing thousands of prospectuses a year has only a year of 10-Qs there;
# older ones sit in numbered pages. Read pages until this much history is in hand.
_HISTORY_DAYS = 3 * 365 + 30
_MAX_OLDER_PAGES = 4
_PAGE_NAME = re.compile(r"CIK\d{10}-submissions-\d{3}\.json")
_PERIODIC_FORMS = frozenset({"10-Q", "10-K", "10-Q/A", "10-K/A"})
_MAX_RETRIES = 3
_DEFAULT_RETRY_DELAY_SECONDS = 1.0
_MAX_RETRY_DELAY_SECONDS = 5.0


class _RateLimiter:
    """Space requests at least ``min_interval`` apart across threads.

    Each caller reserves the next free slot under the lock, then sleeps outside
    it, so concurrent workers queue instead of all reading the same timestamp.
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._min_interval
        wait = slot - now
        if wait > 0:
            time.sleep(wait)


# EDGAR's fair-access limit is per host, so every client in the process shares one
# limiter per rate: a new client per turn must not reset the budget.
_SHARED_LIMITERS: dict[float, _RateLimiter] = {}
_SHARED_LIMITERS_LOCK = threading.Lock()


def _shared_limiter(min_interval: float) -> _RateLimiter:
    with _SHARED_LIMITERS_LOCK:
        limiter = _SHARED_LIMITERS.get(min_interval)
        if limiter is None:
            limiter = _RateLimiter(min_interval)
            _SHARED_LIMITERS[min_interval] = limiter
        return limiter


class SECClient:
    """HTTP client for SEC EDGAR JSON APIs with rate limiting and retry."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._user_agent = settings.require_user_agent()
        self._timeout = settings.sec_timeout_seconds
        self._owns_client = client is None
        self._client = client
        self._limiter = _shared_limiter(1.0 / settings.sec_max_requests_per_second)
        self._closed = False
        self._client_lock = threading.Lock()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _http(self) -> httpx.Client:
        with self._client_lock:
            if self._client is None:
                self._client = httpx.Client(timeout=self._timeout)
            return self._client

    def _acquire(self) -> None:
        self._limiter.acquire()

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
        valid = validate_submissions_response(payload, cik, details={"url": url, "cik": cik})
        return self._with_history(valid)

    def _with_history(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Append older submission pages until ~3 years of 10-Qs and 10-Ks are covered."""
        filings = payload["filings"]
        recent = filings["recent"]
        pages = filings.get("files")
        if not isinstance(pages, list):
            return payload
        for page in pages[:_MAX_OLDER_PAGES]:
            if _periodic_span_days(recent) >= _HISTORY_DAYS:
                break
            name = page.get("name") if isinstance(page, dict) else None
            if not isinstance(name, str) or not _PAGE_NAME.fullmatch(name):
                break
            older = self._fetch_json(f"{self._settings.sec_base_url}/submissions/{name}")
            if not isinstance(older, dict) or not isinstance(older.get("form"), list):
                break
            _append_page(recent, older)
        return payload

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        url = f"{self._settings.sec_base_url}/api/xbrl/companyfacts/CIK{cik}.json"
        return validate_companyfacts_response(
            self._fetch_json(url), cik, details={"url": url, "cik": cik}
        )


def _periodic_span_days(recent: dict[str, Any]) -> int:
    """Days between the newest and oldest 10-Q/10-K report dates in ``recent``."""
    dates: list[date] = []
    for form, raw in zip(recent.get("form", []), recent.get("reportDate", []), strict=False):
        if form in _PERIODIC_FORMS and isinstance(raw, str):
            try:
                dates.append(date.fromisoformat(raw))
            except ValueError:
                continue
    return (max(dates) - min(dates)).days if dates else 0


def _append_page(recent: dict[str, Any], older: dict[str, Any]) -> None:
    """Extend every column of ``recent`` by an older page, keeping the columns equal."""
    count = len(older["form"])
    for key, values in recent.items():
        if not isinstance(values, list):
            continue
        extra = older.get(key)
        if isinstance(extra, list) and len(extra) == count:
            values.extend(extra)
        else:
            values.extend([""] * count)
