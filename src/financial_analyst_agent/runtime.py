"""Fixture and live runtimes for run_turn."""

import json
import re
from types import SimpleNamespace

from financial_analyst_agent.config import AppMode, Settings, get_settings
from financial_analyst_agent.facts import FixtureFactLookup
from financial_analyst_agent.news import FixtureNewsSearch, TavilyNewsSearch
from financial_analyst_agent.planner import OpenAIStructuredCompleter
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.turn import REPORTED_METRICS, Intent, Runtime

_REPORTED_PHRASES: tuple[tuple[str, str], ...] = (
    ("cost of revenue", "cost_of_revenue"),
    ("operating expenses", "operating_expenses"),
    ("operating income", "operating_income"),
    ("gross profit", "gross_profit"),
    ("net income", "net_income"),
    ("revenue", "revenue"),
    ("income", "net_income"),
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
    issuer = _issuer_from_lookup_query(normalized)
    if issuer:
        return issuer
    return "unknown"


def _companies_from_query(normalized: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for phrase, name in _ISSUER_PHRASES:
        if phrase in normalized and name not in seen:
            found.append(name)
            seen.add(name)
    return found


def _issuer_from_lookup_query(normalized: str) -> str | None:
    metric_phrases = "|".join(
        re.escape(phrase) for phrase, _metric in (*_REPORTED_PHRASES, *_FORMULA_PHRASES)
    )
    match = re.search(
        rf"\b(?:what (?:was|is|were)|whats)\s+(.+?)(?:'s)?\s+(?:{metric_phrases})\b",
        normalized,
    )
    if match is None:
        return None
    issuer = match.group(1).strip(" .,?!'")
    return issuer or None


def _limit_from_query(normalized: str) -> int:
    match = re.search(r"\btop\s+(\d+)\b", normalized)
    if match is None:
        return 10
    return int(match.group(1))


def _normalize_industry_label(raw: str) -> str:
    label = re.split(r"\s+\band\b", raw.strip(), maxsplit=1)[0]
    return label.strip(" .,?!").strip()


def _industry_from_query(normalized: str) -> str:
    for pattern in (
        r"\btop\s+\d+\s+companies\s+in\s+(.+)",
        r"\btop\s+\d+\s+(.+?)\s+companies\b",
        r"\bin\s+(.+)",
        r"\btop\s+\d+\s+(.+)",
    ):
        match = re.search(pattern, normalized)
        if match is not None:
            return _normalize_industry_label(match.group(1))
    return "unknown"


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


def _is_news_query(normalized: str) -> bool:
    if "supply chain" in normalized or "supply-chain" in normalized:
        return True
    return re.search(r"what(?:['’]?s| is) going on", normalized) is not None


FIXTURE_EXPLAIN_ESSAY = (
    "AI can disrupt healthcare by automating imaging review, triage, and documentation. "
    "Common use cases include clinical decision support, administrative coding, "
    "and patient outreach."
)


class FixtureEssayCompleter:
    """Recorded essay so explain and news_and_explain turns stay offline."""

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        if not tool_json:
            return FIXTURE_EXPLAIN_ESSAY
        try:
            payload = json.loads(tool_json)
        except json.JSONDecodeError:
            return FIXTURE_EXPLAIN_ESSAY
        if not isinstance(payload, list):
            return FIXTURE_EXPLAIN_ESSAY
        sentences: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            published = str(item.get("published") or "").strip()
            if not title:
                continue
            sentence = f"{title}: {snippet}" if snippet else title
            if published:
                sentence = f"{sentence} ({published})"
            sentences.append(sentence)
        if not sentences:
            return FIXTURE_EXPLAIN_ESSAY
        return " ".join(sentences)


class DemoCompleter:
    """Injectable fake completer so this slice is demoable without OpenAI."""

    def complete(self, query: str) -> SimpleNamespace:
        normalized = query.strip().casefold()
        metric = _metric_from_query(normalized)
        if "disrupt" in normalized or re.search(r"\bhow can ai\b", normalized):
            return SimpleNamespace(intent=Intent.EXPLAIN, topic=query)
        if _is_news_query(normalized):
            return SimpleNamespace(intent=Intent.NEWS_AND_EXPLAIN, query=query)
        if "compare" in normalized:
            return SimpleNamespace(
                intent=Intent.COMPARE,
                companies=_companies_from_query(normalized),
                metric=metric,
            )
        if re.search(r"\btop\b", normalized):
            industry = _industry_from_query(normalized)
            limit = _limit_from_query(normalized)
            if metric in REPORTED_METRICS:
                return SimpleNamespace(
                    intent=Intent.RANK_AND_LOOKUP,
                    industry=industry,
                    limit=limit,
                    metric=metric,
                )
            return SimpleNamespace(
                intent=Intent.RANK,
                industry=industry,
                limit=limit,
            )
        return SimpleNamespace(
            intent=Intent.LOOKUP,
            company=_company_from_query(normalized),
            metric=metric,
        )


def fixture_runtime() -> Runtime:
    return Runtime(
        completer=DemoCompleter(),
        facts=FixtureFactLookup(),
        ranking=SnapshotRanking.from_path(),
        news=FixtureNewsSearch(),
        essay=FixtureEssayCompleter(),
    )


def live_runtime(settings: Settings | None = None) -> Runtime:
    resolved = settings or get_settings()
    return Runtime(
        completer=OpenAIStructuredCompleter.from_settings(resolved),
        facts=SecFactLookup(resolved),
        ranking=SnapshotRanking.from_path(),
        news=TavilyNewsSearch(resolved),
        essay=FixtureEssayCompleter(),
    )


def build_runtime(settings: Settings | None = None) -> Runtime:
    resolved = settings or get_settings()
    if resolved.app_mode is AppMode.FIXTURE:
        return fixture_runtime()
    return live_runtime(resolved)
