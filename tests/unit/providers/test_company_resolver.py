"""Company identity: ticker, alias, and successor/holdings legal names."""

import pytest

from financial_analyst_agent.domain.errors import AmbiguousCompanyError, CompanyNotFoundError
from financial_analyst_agent.providers.sec.company_resolver import resolve_company


def _tickers_payload() -> dict[str, dict[str, object]]:
    return {
        "0": {"cik_str": 2115436, "ticker": "XOM", "title": "ExxonMobil Holdings Corp"},
        "1": {"cik_str": 2014337, "ticker": "NPT", "title": "Texxon Holding Ltd"},
        "2": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "3": {"cik_str": 1418121, "ticker": "APLE", "title": "Apple Hospitality REIT, Inc."},
        "4": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
        "5": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
        "6": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    }


def test_resolve_operating_name_to_successor_holdings_title() -> None:
    company = resolve_company("ExxonMobil", _tickers_payload())
    assert company.cik == "0002115436"
    assert company.tickers == ["XOM"]
    assert company.name == "ExxonMobil Holdings Corp"


def test_resolve_spaced_legal_name_to_successor_holdings_title() -> None:
    company = resolve_company("Exxon Mobil Corporation", _tickers_payload())
    assert company.cik == "0002115436"
    assert company.tickers == ["XOM"]


def test_resolve_xom_ticker_still_hits_successor() -> None:
    company = resolve_company("XOM", _tickers_payload())
    assert company.cik == "0002115436"
    assert company.tickers == ["XOM"]


def test_resolve_successor_cik_query() -> None:
    company = resolve_company("0002115436", _tickers_payload())
    assert company.cik == "0002115436"
    assert company.tickers == ["XOM"]


def test_resolve_unique_core_prefix_to_successor() -> None:
    company = resolve_company("Exxon", _tickers_payload())
    assert company.cik == "0002115436"
    assert company.tickers == ["XOM"]


def test_resolve_does_not_confuse_texxon_with_exxon() -> None:
    with pytest.raises(CompanyNotFoundError):
        resolve_company("Tex", _tickers_payload())
    company = resolve_company("Texxon", _tickers_payload())
    assert company.cik == "0002014337"
    assert company.tickers == ["NPT"]


def test_resolve_apple_without_inc_is_not_hospitality() -> None:
    company = resolve_company("Apple", _tickers_payload())
    assert company.cik == "0000320193"
    assert company.tickers == ["AAPL"]


def test_resolve_short_prefix_of_apple_is_ambiguous() -> None:
    with pytest.raises(AmbiguousCompanyError):
        resolve_company("Appl", _tickers_payload())
