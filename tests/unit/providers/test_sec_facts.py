"""Successor registrant lookup: try the accession-prefix CIK when needed."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import (
    FilingNotFoundError,
    ProviderError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.sec_facts import SecFactLookup, _related_lookup_ciks
from helpers import make_filing

SUCCESSOR_CIK = "0002115436"
PREDECESSOR_CIK = "0000034088"
ACCESSION = "0000034088-26-000093"


def test_related_lookup_ciks_includes_accession_filer() -> None:
    filings = [
        make_filing(
            accession_number=ACCESSION,
            filed_date=date(2026, 8, 3),
            report_date=date(2026, 6, 30),
            primary_document="xom-20260630.htm",
        )
    ]
    assert _related_lookup_ciks(SUCCESSOR_CIK, filings) == (SUCCESSOR_CIK, PREDECESSOR_CIK)


def test_related_lookup_ciks_skips_matching_accession_prefix() -> None:
    filings = [
        make_filing(
            accession_number="0002115436-26-000001",
            filed_date=date(2026, 8, 3),
            report_date=date(2026, 6, 30),
        )
    ]
    assert _related_lookup_ciks(SUCCESSOR_CIK, filings) == (SUCCESSOR_CIK,)


def _submissions(cik: str, accession: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "name": "Exxon Mobil Corporation",
        "tickers": ["XOM"],
        "filings": {
            "recent": {
                "form": ["10-Q"],
                "accessionNumber": [accession],
                "filingDate": ["2026-08-03"],
                "reportDate": ["2026-06-30"],
                "primaryDocument": ["xom-20260630.htm"],
            }
        },
    }


def _empty_facts(cik: str) -> dict[str, object]:
    return {"cik": int(cik), "entityName": "Exxon Mobil Corporation", "facts": {"us-gaap": {}}}


def _quarterly_net_income_facts(cik: str, accession: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "entityName": "Exxon Mobil Corporation",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-04-01",
                                "end": "2026-06-30",
                                "val": 14525000000,
                                "accn": accession,
                                "form": "10-Q",
                                "filed": "2026-08-03",
                            }
                        ]
                    }
                }
            }
        },
    }


def _submissions_two_quarters(cik: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "name": "Exxon Mobil Corporation",
        "tickers": ["XOM"],
        "filings": {
            "recent": {
                "form": ["10-Q", "10-Q"],
                "accessionNumber": ["0000034088-26-000093", "0000034088-26-000050"],
                "filingDate": ["2026-08-03", "2026-05-05"],
                "reportDate": ["2026-06-30", "2026-03-31"],
                "primaryDocument": ["xom-20260630.htm", "xom-20260331.htm"],
            }
        },
    }


def _two_quarter_net_income_facts(cik: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "entityName": "Exxon Mobil Corporation",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-04-01",
                                "end": "2026-06-30",
                                "val": 14525000000,
                                "accn": "0000034088-26-000093",
                                "form": "10-Q",
                                "filed": "2026-08-03",
                            },
                            {
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "val": 7713000000,
                                "accn": "0000034088-26-000050",
                                "form": "10-Q",
                                "filed": "2026-05-05",
                            },
                        ]
                    }
                }
            }
        },
    }


def test_sec_fact_lookup_named_report_date_returns_that_quarter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 34088,
                        "ticker": "XOM",
                        "title": "Exxon Mobil Corporation",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions_two_quarters(PREDECESSOR_CIK))
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_two_quarter_net_income_facts(PREDECESSOR_CIK))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    fact = lookup.get_financials(
        "XOM",
        "net_income",
        report_date=date(2026, 3, 31),
    )
    assert fact.value == Decimal("7713000000")
    assert fact.end_date == date(2026, 3, 31)
    assert fact.accession_number == "0000034088-26-000050"


def test_latest_steps_back_past_filings_companyfacts_lacks() -> None:
    submissions = _submissions_two_quarters(PREDECESSOR_CIK)
    recent = submissions["filings"]["recent"]  # type: ignore[index]
    recent["form"].insert(0, "10-Q")
    recent["accessionNumber"].insert(0, "0000034088-26-000120")
    recent["filingDate"].insert(0, "2026-11-03")
    recent["reportDate"].insert(0, "2026-09-30")
    recent["primaryDocument"].insert(0, "xom-20260930.htm")
    facts = _two_quarter_net_income_facts(PREDECESSOR_CIK)
    usd = facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]  # type: ignore[index]
    del usd[0]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={"0": {"cik_str": 34088, "ticker": "XOM", "title": "Exxon Mobil Corporation"}},
            )
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=submissions)
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=facts)
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))

    fact = SecFactLookup(settings, client=client).get_financials("XOM", "net_income")

    assert fact.end_date == date(2026, 3, 31)
    assert fact.value == Decimal("7713000000")
    assert fact.newer_filing_end == date(2026, 9, 30)


def test_sec_fact_lookup_named_report_date_missing_does_not_use_latest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 34088,
                        "ticker": "XOM",
                        "title": "Exxon Mobil Corporation",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions_two_quarters(PREDECESSOR_CIK))
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_two_quarter_net_income_facts(PREDECESSOR_CIK))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    with pytest.raises(UnsupportedQuarterlyFactError) as exc_info:
        lookup.get_financials("XOM", "net_income", report_date=date(2025, 12, 31))
    assert "2025-12-31" in str(exc_info.value.details.get("report_date", ""))



def _empty_facts(cik: str) -> dict[str, object]:
    return {"cik": int(cik), "entityName": "Exxon Mobil Corporation", "facts": {"us-gaap": {}}}


def _quarterly_net_income_facts(cik: str, accession: str) -> dict[str, object]:
    return {
        "cik": int(cik),
        "entityName": "Exxon Mobil Corporation",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2026-04-01",
                                "end": "2026-06-30",
                                "val": 14525000000,
                                "accn": accession,
                                "form": "10-Q",
                                "filed": "2026-08-03",
                            }
                        ]
                    }
                }
            }
        },
    }


def test_sec_fact_lookup_uses_accession_filer_when_successor_has_no_quarter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_empty_facts(SUCCESSOR_CIK))
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_quarterly_net_income_facts(PREDECESSOR_CIK, ACCESSION))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    fact = lookup.get_financials("ExxonMobil", "net_income")
    assert isinstance(fact, FinancialFact)
    assert fact.cik == PREDECESSOR_CIK
    assert fact.ticker == "XOM"
    assert fact.value == Decimal("14525000000")
    assert fact.concept == "NetIncomeLoss"
    assert fact.accession_number == ACCESSION


def test_sec_fact_lookup_uses_accession_filer_when_successor_companyfacts_are_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(404, json={"error": "not found"})
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            return httpx.Response(200, json=_quarterly_net_income_facts(PREDECESSOR_CIK, ACCESSION))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    fact = lookup.get_financials("ExxonMobil", "net_income")
    assert isinstance(fact, FinancialFact)
    assert fact.cik == PREDECESSOR_CIK
    assert fact.ticker == "XOM"
    assert fact.value == Decimal("14525000000")
    assert fact.concept == "NetIncomeLoss"
    assert fact.accession_number == ACCESSION


def test_sec_fact_lookup_does_not_fallback_on_companyfacts_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(400, json={"error": "bad request"})
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)
    with pytest.raises(ProviderError) as exc_info:
        lookup.get_financials("ExxonMobil", "net_income")
    assert exc_info.value.details.get("status_code") == 400


def test_sec_fact_lookup_converts_exhausted_companyfacts_404s_to_missing_fact() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if "/companyfacts/" in path:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = SecFactLookup(settings, client=client)

    with pytest.raises(UnsupportedQuarterlyFactError) as exc_info:
        lookup.get_financials("ExxonMobil", "net_income")

    assert exc_info.value.details == {"metric": "net_income"}


def test_sec_fact_lookup_maps_missing_quarterly_filings_to_unsupported_fact() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            payload = _submissions(SUCCESSOR_CIK, ACCESSION)
            filings = payload["filings"]
            assert isinstance(filings, dict)
            recent = filings["recent"]
            assert isinstance(recent, dict)
            recent["form"] = ["10-K"]
            return httpx.Response(200, json=payload)
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_empty_facts(SUCCESSOR_CIK))
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    lookup = SecFactLookup(
        settings,
        client=SECClient(
            settings,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )

    with pytest.raises(UnsupportedQuarterlyFactError) as exc_info:
        lookup.get_financials("ExxonMobil", "net_income")

    assert not isinstance(exc_info.value, FilingNotFoundError)
    # A lone 10-K with no fiscal-year amount has no quarter to derive (ADR 0007).
    assert "quarter" in str(exc_info.value)


def test_sec_fact_lookup_reuses_sec_payloads_across_get_financials_calls() -> None:
    counts = {"tickers": 0, "submissions": 0, "companyfacts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            counts["tickers"] += 1
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            counts["submissions"] += 1
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            counts["companyfacts"] += 1
            return httpx.Response(200, json=_empty_facts(SUCCESSOR_CIK))
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            counts["companyfacts"] += 1
            return httpx.Response(
                200, json=_quarterly_net_income_facts(PREDECESSOR_CIK, ACCESSION)
            )
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    lookup = SecFactLookup(
        settings,
        client=SECClient(
            settings,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )

    first = lookup.get_financials("ExxonMobil", "net_income")
    second = lookup.get_financials("ExxonMobil", "net_income")

    assert first.value == second.value == Decimal("14525000000")
    assert counts == {"tickers": 1, "submissions": 1, "companyfacts": 2}


def test_sec_fact_lookup_reuses_companyfacts_404_across_get_financials_calls() -> None:
    counts = {"companyfacts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/company_tickers.json"):
            return httpx.Response(
                200,
                json={
                    "0": {
                        "cik_str": 2115436,
                        "ticker": "XOM",
                        "title": "ExxonMobil Holdings Corp",
                    }
                },
            )
        if path.endswith(f"/submissions/CIK{SUCCESSOR_CIK}.json"):
            return httpx.Response(200, json=_submissions(SUCCESSOR_CIK, ACCESSION))
        if path.endswith(f"/companyfacts/CIK{SUCCESSOR_CIK}.json"):
            counts["companyfacts"] += 1
            return httpx.Response(404, json={"error": "not found"})
        if path.endswith(f"/companyfacts/CIK{PREDECESSOR_CIK}.json"):
            counts["companyfacts"] += 1
            return httpx.Response(
                200, json=_quarterly_net_income_facts(PREDECESSOR_CIK, ACCESSION)
            )
        return httpx.Response(404, json={"error": path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    lookup = SecFactLookup(
        settings,
        client=SECClient(
            settings,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ),
    )

    first = lookup.get_financials("ExxonMobil", "net_income")
    second = lookup.get_financials("ExxonMobil", "net_income")

    assert first.value == second.value == Decimal("14525000000")
    assert counts == {"companyfacts": 2}


def test_a_listing_on_the_ineligible_list_is_not_looked_up() -> None:
    from financial_analyst_agent.domain.errors import IneligibleIssuerError

    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(
                200,
                json={"0": {"cik_str": 1287750, "ticker": "ARCC", "title": "ARES CAPITAL CORP"}},
            )
        return httpx.Response(404, json={"error": request.url.path})

    settings = Settings(
        sec_user_agent="FinancialAnalystAgent (dev@example.com)",
        sec_max_requests_per_second=5.0,
    )
    client = SECClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
    lookup = SecFactLookup(settings, client=client)
    with pytest.raises(IneligibleIssuerError) as exc_info:
        lookup.get_financials("ARCC", "eps_diluted")
    assert "not an operating company" in str(exc_info.value)
    assert not any("submissions" in path or "companyfacts" in path for path in requested)


def test_submissions_read_older_pages_until_three_years_are_covered() -> None:
    newest = {
        "cik": 19617,
        "name": "JPMorgan Chase & Co.",
        "tickers": ["JPM"],
        "filings": {
            "recent": {
                "form": ["424B2", "10-Q"],
                "accessionNumber": ["0000019617-26-000900", "0000019617-26-000800"],
                "filingDate": ["2026-09-01", "2026-08-03"],
                "reportDate": ["", "2026-06-30"],
                "primaryDocument": ["a.htm", "jpm-20260630.htm"],
            },
            "files": [
                {"name": "CIK0000019617-submissions-001.json"},
                {"name": "CIK0000019617-submissions-002.json"},
                {"name": "../../etc/passwd"},
            ],
        },
    }
    pages = {
        "CIK0000019617-submissions-001.json": {
            "form": ["10-Q"],
            "accessionNumber": ["0000019617-25-000615"],
            "filingDate": ["2025-08-05"],
            "reportDate": ["2025-06-30"],
            "primaryDocument": ["jpm-20250630.htm"],
        },
        "CIK0000019617-submissions-002.json": {
            "form": ["10-K"],
            "accessionNumber": ["0000019617-23-000100"],
            "filingDate": ["2023-02-21"],
            "reportDate": ["2022-12-31"],
        },
    }
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        requested.append(name)
        if name == "CIK0000019617.json":
            return httpx.Response(200, json=newest)
        return httpx.Response(200, json=pages[name])

    settings = Settings(sec_user_agent="FinancialAnalystAgent (dev@example.com)")
    client = SECClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))

    recent = client.get_submissions("0000019617")["filings"]["recent"]

    assert recent["accessionNumber"][-2:] == ["0000019617-25-000615", "0000019617-23-000100"]
    # Every column stays the same length, filling a column a page lacks.
    assert {len(column) for column in recent.values()} == {4}
    assert recent["primaryDocument"][-1] == ""
    assert "passwd" not in " ".join(requested)


def test_periodic_filings_are_rebuilt_from_company_facts() -> None:
    from financial_analyst_agent.sec_facts import filings_from_company_facts

    def fact(
        end: str, accn: str, form: str = "10-Q", filed: str = "2025-08-05"
    ) -> dict[str, object]:
        return {"end": end, "val": 1, "accn": accn, "form": form, "filed": filed}

    payload = {
        "facts": {
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [fact("2025-07-31", "0000019617-25-000615")]}
                }
            },
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            fact("2025-06-30", "0000019617-25-000615"),
                            fact("2024-06-30", "0000019617-25-000615"),
                            fact("2025-06-30", "0000019617-25-000615"),
                            fact("2024-12-31", "0000019617-25-000100", "10-K", "2025-02-14"),
                            fact("2024-12-31", "0000019617-25-000200", "8-K", "2025-01-15"),
                        ]
                    }
                }
            },
        }
    }

    filings = {filing.accession_number: filing for filing in filings_from_company_facts(payload)}

    assert set(filings) == {"0000019617-25-000615", "0000019617-25-000100"}
    # The cover page's later shares date is not the report's period.
    assert filings["0000019617-25-000615"].report_date == date(2025, 6, 30)
    assert filings["0000019617-25-000100"].form == "10-K"
