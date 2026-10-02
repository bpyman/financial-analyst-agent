"""Every SEC request ends in bounded time and memory, and SEC's own pauses are kept."""

import gzip
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.providers.sec import client as sec_client
from financial_analyst_agent.providers.sec.client import SEC_PAUSE, SECClient, sec_turn_budget

FILING = "<html><body>" + "Item 2. Management's Discussion and Analysis. " * 300 + "</body></html>"
URL_PREFIX = "https://data.sec.gov"


def _client(handler: Callable[[httpx.Request], httpx.Response], **overrides: Any) -> SECClient:
    values: dict[str, Any] = {
        "_env_file": None,
        "sec_user_agent": "OnfileTests (tests@example.com)",
        "sec_max_requests_per_second": 5,
    }
    values.update(overrides)
    transport = httpx.MockTransport(handler)
    return SECClient(Settings(**values), client=httpx.Client(transport=transport))


class _Drip(httpx.SyncByteStream):
    """A body sent a byte at a time: no single read is ever slow."""

    def __init__(self, body: bytes, interval: float) -> None:
        self._body = body
        self._interval = interval

    def __iter__(self) -> Iterator[bytes]:
        for index in range(len(self._body)):
            time.sleep(self._interval)
            yield self._body[index : index + 1]


class _Chunks(httpx.SyncByteStream):
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __iter__(self) -> Iterator[bytes]:
        for start in range(0, len(self._body), 65536):
            yield self._body[start : start + 65536]


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    real_sleep = time.sleep
    monkeypatch.setattr(sec_client.time, "sleep", lambda seconds: real_sleep(min(seconds, 0.01)))


def test_a_dripping_response_ends_at_the_request_deadline() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, stream=_Drip(b'{"cik": 1}' * 100, 0.02))

    client = _client(handler, sec_request_deadline_seconds=0.3)
    started = time.monotonic()
    with pytest.raises(ProviderError, match="took too long"):
        client.get_company_tickers()

    assert time.monotonic() - started < 2
    assert len(calls) == 1


def test_a_hung_request_is_not_asked_again() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        raise httpx.ReadTimeout("hung", request=request)

    with pytest.raises(ProviderError, match="timed out"):
        _client(handler).get_submissions("0000320193")
    assert len(calls) == 1


def test_a_spent_turn_budget_refuses_requests_before_sending_them() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={})

    client = _client(handler)
    with sec_turn_budget(0.0), pytest.raises(ProviderError, match="time for SEC requests"):
        client.get_company_tickers()
    assert calls == []


def test_retry_after_pauses_every_request_in_the_process() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(429, headers={"Retry-After": "60"}, json={})

    client = _client(handler)
    with pytest.raises(ProviderError, match="pause"):
        client.get_company_facts("0000320193")
    with pytest.raises(ProviderError, match="pause"):
        _client(handler).get_submissions("0000789019")

    assert calls == ["/api/xbrl/companyfacts/CIK0000320193.json"]
    assert 55 < SEC_PAUSE.remaining() <= 60


def test_secs_undeclared_tool_page_trips_a_ten_minute_breaker() -> None:
    calls: list[str] = []
    page = (
        b"<html><body><h1>Your Request Originates from an Undeclared Automated Tool</h1>"
        b"</body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(403, content=page, headers={"Content-Type": "text/html"})

    with pytest.raises(ProviderError, match="refused"):
        _client(handler).get_company_facts("0000320193")
    with pytest.raises(ProviderError, match="pause"):
        _client(handler).get_company_facts("0000789019")

    assert len(calls) == 1
    assert 590 < SEC_PAUSE.remaining() <= 600


def test_an_ordinary_403_does_not_pause_sec() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"<html>Forbidden</html>")

    with pytest.raises(ProviderError, match="client error"):
        _client(handler).get_company_facts("0000320193")
    assert SEC_PAUSE.remaining() == 0


def test_a_compressed_bomb_stops_at_the_size_cap() -> None:
    bomb = gzip.compress(b'{"cik": 1, "pad": "' + b"0" * (8 * 1024 * 1024) + b'"}')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=_Chunks(bomb))

    with pytest.raises(ProviderError, match="too large"):
        _client(handler, sec_max_response_bytes=2 * 1024 * 1024).get_company_tickers()


def test_a_compressed_response_under_the_cap_is_read() -> None:
    body = gzip.compress(b'{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=_Chunks(body))

    assert _client(handler).get_company_tickers()["0"]["ticker"] == "AAPL"


@pytest.mark.parametrize(
    "body",
    [b"", b"<html><body>Service Unavailable</body></html>", b"x" * 20_000],
    ids=["empty", "error page", "not html"],
)
def test_an_empty_or_error_page_is_not_a_filing(body: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"Content-Type": "text/html"})

    with pytest.raises(ProviderError, match="no usable filing document"):
        _client(handler).get_filing_document("0000789019", "0000789019-26-000001", "a.htm")


def test_a_filing_document_is_returned_as_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=FILING.encode(), headers={"Content-Type": "text/html; charset=utf-8"}
        )

    text = _client(handler).get_filing_document("0000789019", "0000789019-26-000001", "a.htm")
    assert text == FILING
