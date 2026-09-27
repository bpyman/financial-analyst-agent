"""The rules planner: maps a question to a plan without a model.

The recorded runtime always uses it, and the live runtime does whenever the
deployment does not call OpenAI, so it has to read everyday questions: company
names and tickers from the ranking snapshot, misspellings, "X or Y", growth,
rankings by industry, and follow-ups that lean on the current analysis.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.issuer_index import CompanyMention, IssuerIndex
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase
from financial_analyst_agent.turn import ALLOWED_METRICS, Intent
from financial_analyst_agent.universe import DEFAULT_SNAPSHOT_PATH, load_universe_snapshot

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
    # The rest of the recorded cassette, so the demo answers by name for every
    # company it holds (the landing page's own examples name Eli Lilly and Merck).
    ("nvidia", "NVDA"),
    ("nvda", "NVDA"),
    ("broadcom", "AVGO"),
    ("avgo", "AVGO"),
    ("eli lilly", "LLY"),
    ("lilly", "LLY"),
    ("lly", "LLY"),
    ("advanced micro devices", "AMD"),
    ("amd", "AMD"),
    ("jpmorgan", "JPM"),
    ("jp morgan", "JPM"),
    ("jpm", "JPM"),
    ("johnson & johnson", "JNJ"),
    ("johnson and johnson", "JNJ"),
    ("j&j", "JNJ"),
    ("jnj", "JNJ"),
    ("abbvie", "ABBV"),
    ("abbv", "ABBV"),
    ("oracle", "ORCL"),
    ("orcl", "ORCL"),
    ("palantir", "PLTR"),
    ("pltr", "PLTR"),
    ("cisco", "CSCO"),
    ("csco", "CSCO"),
    ("bank of america", "BAC"),
    ("merck", "MRK"),
    ("mrk", "MRK"),
    ("applied materials", "AMAT"),
    ("amat", "AMAT"),
    ("unitedhealth", "UNH"),
    ("united health", "UNH"),
    ("unh", "UNH"),
    ("goldman sachs", "GS"),
    ("goldman", "GS"),
    ("wells fargo", "WFC"),
    ("wfc", "WFC"),
    ("thermo fisher", "TMO"),
    ("amgen", "AMGN"),
    ("amgn", "AMGN"),
    ("gilead", "GILD"),
    ("gild", "GILD"),
    ("abbott", "ABT"),
    ("pfizer", "PFE"),
    ("pfe", "PFE"),
    ("danaher", "DHR"),
)
_ACCESSION_PATTERN = re.compile(r"\d{10}-\d{2}-\d{6}")
RECORDED_FILING_OLDER = "0000950170-25-061046"
RECORDED_FILING_NEWER = "0001193125-26-191507"


def _company_from_query(normalized: str) -> str:
    companies = _companies_from_query(normalized)
    if companies:
        return companies[0]
    issuer = _issuer_from_lookup_query(normalized)
    if issuer:
        return issuer
    return "unknown"


def _companies_from_query(normalized: str) -> list[str]:
    """Issuers named in the query, in the order the analyst named them.

    Whole words only, so "gm" does not match inside "algorithm".
    """
    first_seen: dict[str, int] = {}
    for phrase, name in _ISSUER_PHRASES:
        match = re.search(rf"(?<![\w&]){re.escape(phrase)}(?![\w&])", normalized)
        if match is None:
            continue
        if name not in first_seen or match.start() < first_seen[name]:
            first_seen[name] = match.start()
    return sorted(first_seen, key=first_seen.__getitem__)


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
    resolved = resolve_metric_phrase(normalized)
    if resolved.kind == "unique" and resolved.metric in (
        "eps_diluted",
        "eps_basic",
        "operating_cash_flow",
        "capital_expenditure",
        "free_cash_flow",
    ):
        # Catalog phrases the older tables below predate ("EPS", "free cash flow").
        return resolved.metric
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
    return (
        re.search(
            r"what(?:['’]?s| is) (?:going on|happening)|\bnews\b|\bheadlines?\b"
            r"|\blatest on\b|\bin the news\b",
            normalized,
        )
        is not None
    )


_FILING_WORDS = (
    "md&a",
    "mda",
    "risk factor",
    "management discussion",
    "management's discussion",
    "10-q",
    "10q",
    "filing",
    "disclosure",
    "quarterly report",
)


def _is_filing_change_query(normalized: str) -> bool:
    asks_change = re.search(
        r"what(?:['’]?s| has| is)? (?:changed|new)|filing change|\bchanges? (?:in|to)\b"
        r"|\bdiff(?:erence)?s? (?:in|between)\b",
        normalized,
    )
    return asks_change is not None and any(token in normalized for token in _FILING_WORDS)


def _filing_change_plan(query: str, normalized: str) -> SimpleNamespace:
    accessions = _ACCESSION_PATTERN.findall(query)
    older = accessions[0] if len(accessions) >= 2 else ""
    newer = accessions[1] if len(accessions) >= 2 else ""
    section = "mda"
    if not any(token in normalized for token in ("md&a", "mda", "management", "risk")):
        # "What changed in Apple's 10-Q?" asks about the filing: both sections.
        section = "mda and risk_factors"
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


_RANK_WORDS = re.compile(r"\b(?:top|biggest|largest|leading)\b")
_ADD_WORDING = re.compile(r"^\s*(?:and|also|plus|with|include|now add|add)\b|\b(?:their|its)\b")
_SWAP_WORDING = re.compile(
    r"^\s*(?:what about|how about|and what about|same for|now|ok|okay)\b"
    r"|\binstead\b|^\s*(?:just|only)\b|^\s*by\b"
)
_TOP_N = re.compile(r"\b(?:only |just )?(?:the )?top\s+(\d+)\b")
_LIMIT_WORDS = re.compile(
    r"\b(?:top|biggest|largest|leading)\s+(\d+)\b|\b(\d+)\s+(?:biggest|largest)\b"
)
_FOLLOW_UP_MAX_WORDS = 7
_METRIC_WORDS = frozenset(
    word
    for phrase, _metric in (*_REPORTED_PHRASES, *_FORMULA_PHRASES)
    for word in phrase.split()
) | frozenset({"eps", "earnings", "share", "cash", "flow", "free", "capex", "capital", "spending"})


@lru_cache(maxsize=4)
def _index_for(path: Path, _mtime_ns: int) -> IssuerIndex:
    snapshot = load_universe_snapshot(path)
    return IssuerIndex.build(snapshot.companies, _ISSUER_PHRASES)


def issuer_index(path: Path | None = None) -> IssuerIndex:
    """The index for a snapshot file, rebuilt when the file changes."""
    resolved = path or DEFAULT_SNAPSHOT_PATH
    return _index_for(resolved, resolved.stat().st_mtime_ns)


def recorded_issuer_index() -> IssuerIndex:
    return issuer_index(FIXTURE_UNIVERSE_SNAPSHOT_PATH)


def _limit(normalized: str) -> int:
    match = _LIMIT_WORDS.search(normalized)
    if match is None:
        return _limit_from_query(normalized)
    return int(match.group(1) or match.group(2))


def _ranked_industry(normalized: str) -> str:
    """The group a ranking names: "top 5 semiconductor companies", "biggest banks"."""
    text = re.sub(r"\b(?:by|in terms of|ranked by)\b.*$", "", normalized)
    text = re.split(r"\s+(?:and|with|plus)\s+|,", text, maxsplit=1)[0]
    match = re.search(
        r"\b(?:top|biggest|largest|leading)\s+(?:\d+\s+)?(?:companies\s+in\s+(?:the\s+)?)?(.+)$",
        text,
    ) or re.search(r"\b\d+\s+(?:biggest|largest)\s+(.+)$", text)
    if match is None:
        return _industry_from_query(normalized)
    label = re.sub(r"\s+(?:companies|stocks|firms|names)\b.*$", "", match.group(1))
    label = re.sub(r"\b(?:the|us|u s|american)\s+", "", label)
    label = label.strip(" .,?!")
    return label or _industry_from_query(normalized)


def _mention_note(index: IssuerIndex, mention: CompanyMention) -> str:
    name = short_name(index.display_name(mention.query)) or mention.query
    return f"Showing {name} for “{mention.typed}”."


class DemoCompleter:
    """Rules planner; see the module docstring.

    ``index`` names the companies it recognizes: the recorded cassette's by
    default, the live snapshot's on the live runtime.
    """

    def __init__(self, index: IssuerIndex | None = None) -> None:
        self._index = index

    @property
    def index(self) -> IssuerIndex:
        if self._index is None:
            self._index = recorded_issuer_index()
        return self._index

    def complete(self, query: str, current_spec: object = None) -> Any:
        normalized = query.strip().casefold()
        metric = _metric_from_query(normalized)
        mentions = self.index.find(query)
        notes: tuple[str, ...] = ()
        if not mentions:
            mentions = self.index.correct(query, ignore=_METRIC_WORDS)
            notes = tuple(_mention_note(self.index, mention) for mention in mentions)
        companies = [mention.query for mention in mentions]

        if _is_filing_change_query(normalized):
            plan = _filing_change_plan(query, normalized)
            if companies:
                plan.company = companies[0]
            plan.notes = notes
            return plan
        if "disrupt" in normalized or re.search(
            r"\bhow (?:can|could|will|might|would) ai\b", normalized
        ):
            return SimpleNamespace(intent=Intent.EXPLAIN, topic=query)
        if _is_exploratory_query(normalized):
            return SimpleNamespace(intent=Intent.EXPLORATORY_RESEARCH, topic=query)
        if _is_news_query(normalized):
            return SimpleNamespace(intent=Intent.NEWS_AND_EXPLAIN, query=query)

        spec = current_spec if isinstance(current_spec, AnalysisSpec) else None
        if spec is not None:
            follow_up = _follow_up(normalized, companies, metric, spec)
            if follow_up is not None:
                return follow_up

        if len(companies) < 2 and _RANK_WORDS.search(normalized):
            industry = _ranked_industry(normalized)
            limit = _limit(normalized)
            if metric in ALLOWED_METRICS:
                return SimpleNamespace(
                    intent=Intent.RANK_AND_LOOKUP, industry=industry, limit=limit, metric=metric
                )
            return SimpleNamespace(intent=Intent.RANK, industry=industry, limit=limit)
        if len(companies) >= 2 or re.search(r"\b(?:compare|vs|versus)\b", normalized):
            return SimpleNamespace(
                intent=Intent.COMPARE, companies=companies, metric=metric, notes=notes
            )
        company = companies[0] if companies else _company_from_query(normalized)
        return SimpleNamespace(intent=Intent.LOOKUP, company=company, metric=metric, notes=notes)


def _follow_up(
    normalized: str, companies: list[str], metric: str, spec: AnalysisSpec
) -> SpecPatch | None:
    """Short edits that lean on the current analysis ("and net margin", "what about MSFT?")."""
    if len(normalized.split()) > _FOLLOW_UP_MAX_WORDS:
        return None
    top = _TOP_N.search(normalized)
    if (
        top is not None
        and spec.constituents is not None
        and not companies
        and re.fullmatch(r"(?:only |just |show )?(?:the )?top\s+\d+", normalized.strip(" .?!"))
    ):
        return SpecPatch(
            mode="extend", ranked_request=(spec.constituents.industry, int(top.group(1)))
        )
    if _RANK_WORDS.search(normalized):
        # "largest pharma companies by net income" is a new ranking, not an edit.
        return None
    if companies and metric == "unknown" and spec.companies:
        if _ADD_WORDING.search(normalized):
            return SpecPatch(mode="extend", add_companies=tuple(companies))
        if _SWAP_WORDING.search(normalized) or len(normalized.split()) <= 2:
            return SpecPatch(
                mode="extend",
                remove_companies=tuple(company.query for company in spec.companies),
                add_companies=tuple(companies),
            )
        return None
    if companies or metric not in ALLOWED_METRICS:
        return None
    if not (spec.companies or spec.constituents is not None):
        return None
    if _SWAP_WORDING.search(normalized) and not re.search(r"\b(?:their|its)\b", normalized):
        return SpecPatch(
            mode="extend",
            add_metrics=(metric,),
            remove_metrics=tuple(m for m in spec.metrics if m != metric),
        )
    return SpecPatch(mode="extend", add_metrics=(metric,))
