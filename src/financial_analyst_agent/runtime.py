"""Fixture and live runtimes for run_turn."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

from financial_analyst_agent.config import AppMode, Settings, get_settings
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.essay import OpenAIEssayCompleter
from financial_analyst_agent.facts import RecordedSECDataSource
from financial_analyst_agent.news import (
    FIXTURE_NEWS_QUERY,
    FIXTURE_RESEARCH_QUERY,
    FixtureNewsSearch,
    TavilyNewsSearch,
)
from financial_analyst_agent.planner import OpenAIStructuredCompleter
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.session import SessionBudget
from financial_analyst_agent.turn import ALLOWED_METRICS, Intent, Runtime

FIXTURE_UNIVERSE_SNAPSHOT_PATH = (
    Path(__file__).parent / "data" / "fixture_universe_snapshot.json"
)

_REPORTED_PHRASES: tuple[tuple[str, str], ...] = (
    ("cost of revenue", "cost_of_revenue"),
    ("operating expenses", "operating_expenses"),
    ("operating income", "operating_income"),
    ("gross profit", "gross_profit"),
    ("research and development", "research_and_development"),
    ("selling general and administrative", "selling_general_and_administrative"),
    ("interest expense", "interest_expense"),
    ("income tax", "income_tax_expense"),
    ("pretax income", "pretax_income"),
    ("pre-tax income", "pretax_income"),
    ("r&d spend", "research_and_development"),
    ("net income", "net_income"),
    ("revenue", "revenue"),
    ("income", "net_income"),
)
_FORMULA_PHRASES: tuple[tuple[str, str], ...] = (
    ("operating margin", "operating_margin"),
    ("gross margin", "gross_margin"),
    ("net margin", "net_margin"),
    ("r&d to sales", "rd_to_sales"),
    ("sg&a ratio", "sga_ratio"),
    ("effective tax rate", "effective_tax_rate"),
    ("interest coverage", "interest_coverage"),
    ("market cap", "market_cap"),
)
_ISSUER_PHRASES: tuple[tuple[str, str], ...] = (
    ("microsoft", "Microsoft"),
    ("msft", "Microsoft"),
    ("apple", "Apple"),
    ("aapl", "Apple"),
    ("alphabet", "Google"),
    ("google", "Google"),
    ("googl", "Google"),
    ("goog", "Google"),
    ("tesla", "Tesla"),
    ("tsla", "Tesla"),
    ("general motors", "GM"),
    ("gm", "GM"),
)
_ACCESSION_PATTERN = re.compile(r"\d{10}-\d{2}-\d{6}")
FIXTURE_FILING_OLDER = "0001193125-25-000099"
FIXTURE_FILING_NEWER = "0001193125-26-191507"


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
    if "hormuz" in normalized and "themes" not in normalized:
        return True
    if "supply chain" in normalized or "supply-chain" in normalized:
        return True
    return re.search(r"what(?:['’]?s| is) going on", normalized) is not None


def _is_filing_change_query(normalized: str) -> bool:
    if "what changed" not in normalized and "filing change" not in normalized:
        return False
    return any(
        token in normalized
        for token in ("md&a", "mda", "risk factor", "management discussion")
    )


def _filing_change_plan(query: str, normalized: str) -> SimpleNamespace:
    accessions = _ACCESSION_PATTERN.findall(query)
    older = accessions[0] if len(accessions) >= 2 else ""
    newer = accessions[1] if len(accessions) >= 2 else ""
    section = "mda"
    if "risk" in normalized and (
        "md&a" in normalized or "mda" in normalized or "both" in normalized
    ):
        section = "mda and risk_factors"
    elif "risk" in normalized:
        section = "risk_factors"
    return SimpleNamespace(
        intent=Intent.FILING_CHANGE,
        company=_company_from_query(normalized),
        older_accession=older,
        newer_accession=newer,
        section=section,
        summarize="summar" in normalized,
    )


def _is_exploratory_query(normalized: str) -> bool:
    if "themes" in normalized and ("coverage" in normalized or "emerging" in normalized):
        return True
    return "exploratory" in normalized


FIXTURE_EXPLAIN_ESSAY = (
    "AI can disrupt healthcare by automating imaging review, triage, and documentation. "
    "Common use cases include clinical decision support, administrative coding, "
    "and patient outreach."
)
FIXTURE_EXPLAIN_QUERY = "How can AI disrupt healthcare?"


class FixtureEssayCompleter:
    """Recorded essay so explain and news_and_explain turns stay offline."""

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        if not tool_json:
            if query.strip().casefold() != FIXTURE_EXPLAIN_QUERY.casefold():
                raise ProviderError("No recorded fixture essay for this prompt")
            return FIXTURE_EXPLAIN_ESSAY
        if query.strip().casefold() not in {
            FIXTURE_NEWS_QUERY.casefold(),
            FIXTURE_RESEARCH_QUERY.casefold(),
        } and "disclosure changes" not in query.casefold():
            raise ProviderError("No recorded fixture news essay for this prompt")
        if "disclosure changes" in query.casefold():
            return (
                "Management described stronger cloud demand and added an "
                "AI product-liability risk."
            )
        try:
            payload = json.loads(tool_json)
        except json.JSONDecodeError as exc:
            raise ProviderError("Recorded fixture news input was invalid") from exc
        if not isinstance(payload, list):
            raise ProviderError("Recorded fixture news input was not a list")
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
            raise ProviderError("Recorded fixture news input contained no usable hits")
        return " ".join(sentences)


class DemoCompleter:
    """Injectable fake completer so this slice is demoable without OpenAI."""

    def complete(self, query: str, current_spec: object = None) -> SimpleNamespace:
        _ = current_spec
        normalized = query.strip().casefold()
        metric = _metric_from_query(normalized)
        if _is_filing_change_query(normalized):
            return _filing_change_plan(query, normalized)
        if "disrupt" in normalized or re.search(r"\bhow can ai\b", normalized):
            return SimpleNamespace(intent=Intent.EXPLAIN, topic=query)
        if _is_exploratory_query(normalized):
            return SimpleNamespace(intent=Intent.EXPLORATORY_RESEARCH, topic=query)
        if _is_news_query(normalized):
            return SimpleNamespace(intent=Intent.NEWS_AND_EXPLAIN, query=query)
        if "compare" in normalized or re.search(r"\bvs\b", normalized):
            return SimpleNamespace(
                intent=Intent.COMPARE,
                companies=_companies_from_query(normalized),
                metric=metric,
            )
        if re.search(r"\btop\b", normalized):
            industry = _industry_from_query(normalized)
            limit = _limit_from_query(normalized)
            if metric in ALLOWED_METRICS:
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
        facts=SecFactLookup(client=RecordedSECDataSource()),
        ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        news=FixtureNewsSearch(),
        essay=FixtureEssayCompleter(),
    )


def live_runtime(
    settings: Settings | None = None,
    *,
    budget: SessionBudget | None = None,
) -> Runtime:
    resolved = settings or get_settings()
    use_openai = not resolved.public_demo or resolved.allow_public_openai
    use_tavily = not resolved.public_demo or resolved.allow_public_tavily
    completer = OpenAIStructuredCompleter.from_settings(resolved) if use_openai else DemoCompleter()
    essay = OpenAIEssayCompleter.from_settings(resolved) if use_openai else FixtureEssayCompleter()
    news = TavilyNewsSearch(resolved) if use_tavily else FixtureNewsSearch()
    cache_dir = resolved.sec_cache_dir or Path(".cache") / "sec"
    client = CachingSECDataSource(SECClient(resolved), Path(cache_dir), budget=budget)
    return Runtime(
        completer=completer,
        facts=SecFactLookup(client=client),
        ranking=SnapshotRanking.from_path(),
        news=news,
        essay=essay,
    )


def runtime_for_kill_switch(
    *,
    enabled: bool,
    settings: Settings | None = None,
    budget: SessionBudget | None = None,
) -> Runtime:
    resolved = settings or get_settings()
    if enabled or (resolved.public_demo and not resolved.demo_live_sec):
        return fixture_runtime()
    return live_runtime(resolved, budget=budget)


def build_runtime(settings: Settings | None = None) -> Runtime:
    resolved = settings or get_settings()
    return runtime_for_kill_switch(
        enabled=resolved.app_mode is AppMode.FIXTURE,
        settings=resolved,
    )
