"""Fixture and live runtimes for run_turn."""

import re
from types import SimpleNamespace

from financial_analyst_agent.config import AppMode, Settings, get_settings
from financial_analyst_agent.facts import FixtureFactLookup
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.turn import Intent, Runtime

_REPORTED_PHRASES: tuple[tuple[str, str], ...] = (
    ("cost of revenue", "cost_of_revenue"),
    ("operating expenses", "operating_expenses"),
    ("operating income", "operating_income"),
    ("gross profit", "gross_profit"),
    ("net income", "net_income"),
    ("revenue", "revenue"),
)
_FORMULA_PHRASES: tuple[tuple[str, str], ...] = (
    ("operating margin", "operating_margin"),
    ("gross margin", "gross_margin"),
    ("net margin", "net_margin"),
)
_ISSUER_PHRASES: tuple[tuple[str, str], ...] = (
    ("microsoft", "Microsoft"),
    ("msft", "Microsoft"),
    ("alphabet", "Google"),
    ("google", "Google"),
    ("googl", "Google"),
    ("goog", "Google"),
)


def _company_from_query(normalized: str) -> str:
    companies = _companies_from_query(normalized)
    if companies:
        return companies[0]
    return "unknown"


def _companies_from_query(normalized: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for phrase, name in _ISSUER_PHRASES:
        if phrase in normalized and name not in seen:
            found.append(name)
            seen.add(name)
    return found


def _metric_from_query(normalized: str) -> str:
    for phrase, metric in _REPORTED_PHRASES:
        if phrase in normalized:
            return metric
    for phrase, metric in _FORMULA_PHRASES:
        if phrase in normalized:
            return metric
    if re.search(r"\broe\b", normalized):
        return "roe"
    if "cost of revenue" not in normalized and re.search(r"\bcosts?\b", normalized):
        return "costs"
    return "unknown"


class DemoCompleter:
    """Injectable fake completer so this slice is demoable without OpenAI."""

    def complete(self, query: str) -> SimpleNamespace:
        normalized = query.strip().casefold()
        metric = _metric_from_query(normalized)
        if "compare" in normalized:
            return SimpleNamespace(
                intent=Intent.COMPARE,
                companies=_companies_from_query(normalized),
                metric=metric,
            )
        return SimpleNamespace(
            intent=Intent.LOOKUP,
            company=_company_from_query(normalized),
            metric=metric,
        )


def fixture_runtime() -> Runtime:
    return Runtime(completer=DemoCompleter(), facts=FixtureFactLookup())


def live_runtime(settings: Settings | None = None) -> Runtime:
    return Runtime(
        completer=DemoCompleter(),
        facts=SecFactLookup(settings or get_settings()),
    )


def build_runtime(settings: Settings | None = None) -> Runtime:
    resolved = settings or get_settings()
    if resolved.app_mode is AppMode.FIXTURE:
        return fixture_runtime()
    return live_runtime(resolved)
