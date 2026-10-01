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

from financial_analyst_agent.filing_change import ACCESSION_PATTERN, requested_sections
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.graph.spec_turn import (
    OVERVIEW_PLAN,
    implied_metrics,
    parse_named_periods,
)
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.issuer_index import (
    CompanyMention,
    IssuerIndex,
    expand_groups,
    normalize,
)
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase
from financial_analyst_agent.turn import ALLOWED_METRICS, Intent
from financial_analyst_agent.universe import (
    DEFAULT_SNAPSHOT_PATH,
    ineligible_issuers,
    load_universe_snapshot,
)

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
# Metrics added after the phrase tables above; the catalog reads their phrases.
_ADDED_METRICS: tuple[str, ...] = (
    "depreciation_amortization",
    "dividends_paid",
    "dividends_per_share",
    "cash",
    "shareholders_equity",
    "ebitda",
    "return_on_equity",
    "pe_ratio",
    "price",
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
        *_ADDED_METRICS,
    ):
        # Catalog phrases the older tables below predate ("EPS", "free cash flow").
        return resolved.metric
    if resolved.kind == "unique" and set(resolved.metrics) & set(_ADDED_METRICS):
        # "Apple cash and EBITDA": the spec binds every metric named.
        return resolved.metrics[0]
    for phrase, metric in _REPORTED_PHRASES:
        if phrase in normalized:
            return metric
    for phrase, metric in _FORMULA_PHRASES:
        if phrase in normalized:
            return metric
    if re.search(r"\brevs?\b", normalized):
        return "revenue"
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
    "10-k",
    "10k",
    "annual report",
    "filing",
    "disclosure",
    "quarterly report",
)


def _is_filing_change_query(normalized: str) -> bool:
    asks_change = re.search(
        r"what(?:['’]?s| has| is)? (?:changed|new)|filing change|\bchanges? (?:in|to)\b"
        r"|\bdiff(?:erence)?s? (?:in|between)\b|\bsummar(?:y|ise|ize)\b",
        normalized,
    )
    return asks_change is not None and (
        any(token in normalized for token in _FILING_WORDS)
        or ACCESSION_PATTERN.search(normalized) is not None
    )


def _filing_change_plan(query: str, normalized: str) -> SimpleNamespace:
    accessions = ACCESSION_PATTERN.findall(query)
    older = accessions[0] if len(accessions) >= 2 else ""
    newer = accessions[1] if len(accessions) >= 2 else ""
    # "What changed in Apple's 10-Q?" names no section: it asks about the filing.
    section = requested_sections(normalized) or "mda and risk_factors"
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


_PEERS = re.compile(
    r"\b(?:peers?|competitors?|rivals?|comparables?|similar (?:companies|firms|to)"
    r"|companies like)\b"
)
_SORT_BY = re.compile(r"^(?:sort|order|rank)(?:ed)?\s+(?:them\s+|it\s+|these\s+)?by\s+.+$")
_LIST_WORDING = re.compile(r"\b(?:vs|versus|compare[ds]?|and|or|against)\b|,")
_RANK_WORDS = re.compile(r"\b(?:top|biggest|largest|leading|rank|ranked|ranking)\b")
# "Which tech company has the highest net margin?" ranks an industry by a metric.
_WHICH_HIGHEST = re.compile(
    r"\bwhich\s+(?P<group>[a-z&][a-z&\- ]*?)\s+(?:companies|company|stocks|stock|firms|firm)?\s*"
    r"(?:has|have|had|is|are|with)\s+the\s+(?:highest|most|biggest|largest|best|greatest|top)\b"
)
_ORDER_WORDING = re.compile(
    r"\b(?:by|in terms of|ranked by|sorted by|with the (?:most|highest|biggest|largest))\b"
)
_ADD_WORDING = re.compile(r"^\s*(?:and|also|plus|with|include|now add|add)\b|\b(?:their|its)\b")
# "compare it to Google", "vs AMD": set a named company beside the current analysis.
_COMPARE_TO_WORDING = re.compile(
    r"^\s*(?:now\s+)?compare[ds]?\s+(?:it|them|this|that|these|those)\s+(?:to|with|against)\b"
    r"|^\s*(?:vs\.?|versus|against)\s"
    r"|^\s*(?:and\s+)?how\s+(?:does\s+it|do\s+they)\s+compare\s+(?:to|with)\b"
)
# "compare them": the companies already on screen (or the last two named), side by side.
_COMPARE_THEM = re.compile(
    r"(?:now\s+|ok\s+|okay\s+)?compare\s+(?:them|the\s+two|both|these|those)"
    r"(?:\s+side\s+by\s+side)?"
)
_LEADING_AND = re.compile(r"^\s*(?:and|also|plus|add)\b")
_SWAP_WORDING = re.compile(
    r"^\s*(?:what about|how about|and what about|same for|now|ok|okay)\b"
    r"|\binstead\b|^\s*(?:just|only)\b|^\s*by\b"
)
_TOP_N = re.compile(r"\b(?:only |just )?(?:the )?top\s+(\d+)\b")
_LIMIT_WORDS = re.compile(
    r"\b(?:top|biggest|largest|leading)\s+(\d+)\b|\b(\d+)\s+(?:biggest|largest)\b"
)
_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "twenty five": 25, "twenty-five": 25, "a dozen": 12, "dozen": 12,
}  # fmt: skip
_COUNT_WORD = "|".join(sorted(map(re.escape, _COUNT_WORDS), key=len, reverse=True))
# "top five banks" is five banks, not Five Below.
_RANK_COUNT_WORD = re.compile(
    rf"\b(top|biggest|largest|leading)\s+({_COUNT_WORD})\b"
    rf"|\b({_COUNT_WORD})\s+(biggest|largest)\b",
    re.IGNORECASE,
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
    index = IssuerIndex.build(snapshot.companies, _ISSUER_PHRASES)
    # Funds are left out of the snapshot, yet "SPY revenue" names one: the
    # lookup then says it is not an operating company (ADR 0001).
    for ticker, name in ineligible_issuers():
        index.add_outside(ticker, name)
    return index


def issuer_index(path: Path | None = None) -> IssuerIndex:
    """The index for a snapshot file, rebuilt when the file changes."""
    resolved = path or DEFAULT_SNAPSHOT_PATH
    return _index_for(resolved, resolved.stat().st_mtime_ns)


def recorded_issuer_index() -> IssuerIndex:
    return issuer_index(FIXTURE_UNIVERSE_SNAPSHOT_PATH)


def _count_words_as_digits(query: str) -> str:
    """ "Top five banks" → "top 5 banks", so the count is read and Five Below is not."""

    def digits(match: re.Match[str]) -> str:
        if match.group(1):
            return f"{match.group(1)} {_COUNT_WORDS[match.group(2).casefold()]}"
        return f"{_COUNT_WORDS[match.group(3).casefold()]} {match.group(4)}"

    return _RANK_COUNT_WORD.sub(digits, query)


def _limit(normalized: str) -> int:
    match = _LIMIT_WORDS.search(normalized)
    if match is None:
        return _limit_from_query(normalized)
    return int(match.group(1) or match.group(2))


def _ranked_industry(normalized: str) -> str:
    """The group a ranking names: "top 5 semiconductor companies", "biggest banks"."""
    text = re.sub(r"\b(?:by|in terms of|ranked by)\b.*$", "", normalized)
    # "oil and gas" is one industry, not a list to cut at "and".
    text = re.sub(r"\boil and gas\b", "oil & gas", text)
    text = re.split(r"\s+(?:and|with|plus)\s+|,", text, maxsplit=1)[0]
    match = re.search(
        r"\b(?:top|biggest|largest|leading|rank(?:ed)?)\s+(?:the\s+)?(?:top\s+)?(?:\d+\s+)?"
        r"(?:companies\s+in\s+(?:the\s+)?)?(.+)$",
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

    def __init__(self, index: IssuerIndex | None = None, *, recorded: bool = False) -> None:
        self._index = index
        self._recorded = recorded

    @property
    def index(self) -> IssuerIndex:
        if self._index is None:
            self._index = recorded_issuer_index()
        return self._index

    @property
    def outside_index(self) -> IssuerIndex | None:
        """The live snapshot's index on the recorded runtime, to name what was not recorded."""
        return issuer_index() if self._recorded else None

    def complete(self, query: str, current_spec: object = None) -> Any:
        query = _count_words_as_digits(expand_groups(query))
        normalized = query.strip().casefold()
        metric = _metric_from_query(normalized)
        mentions = self.index.find(query)
        notes: tuple[str, ...] = ()
        if not mentions:
            mentions = self.index.correct(query, ignore=_METRIC_WORDS)
            notes = tuple(_mention_note(self.index, mention) for mention in mentions)
        elif _LIST_WORDING.search(normalized):
            # "Microsoft vs Aple": a misspelled name beside a correct one still counts.
            named_words = frozenset(
                word for mention in mentions for word in normalize(mention.typed).split()
            )
            known = {mention.query for mention in mentions}
            extra = [
                mention
                for mention in self.index.correct(query, ignore=_METRIC_WORDS | named_words)
                if mention.query not in known
            ]
            if extra:
                mentions = sorted([*mentions, *extra], key=lambda mention: mention.start)
                notes = tuple(_mention_note(self.index, mention) for mention in extra)
        companies = [mention.query for mention in mentions]

        if _is_filing_change_query(normalized):
            plan = _filing_change_plan(query, normalized)
            if companies:
                plan.company = companies[0]
                # One company's filings are compared at a time; the turn says so.
                plan.other_companies = tuple(companies[1:])
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

        which = _WHICH_HIGHEST.search(normalized) if not companies else None
        if len(companies) < 2 and (_RANK_WORDS.search(normalized) or which is not None):
            industry = which.group("group") if which is not None else _ranked_industry(normalized)
            limit = _limit(normalized)
            if metric in ALLOWED_METRICS:
                ordered = metric != "market_cap" and (
                    which is not None or bool(_ORDER_WORDING.search(normalized))
                )
                return SimpleNamespace(
                    intent=Intent.RANK_AND_LOOKUP,
                    industry=industry,
                    limit=limit,
                    metric=metric,
                    # "top 5 banks by net income" orders by it; "and their net income" does not.
                    order_by_metric=ordered,
                )
            return SimpleNamespace(intent=Intent.RANK, industry=industry, limit=limit)
        if len(companies) == 1 and _PEERS.search(normalized):
            # "Compare Nvidia to its peers": the conversation adds the peers.
            return SimpleNamespace(
                intent=Intent.COMPARE,
                companies=companies,
                metric=metric if metric != "unknown" else OVERVIEW_PLAN,
                notes=notes,
                peers=True,
            )
        # "Meta margin Q2 2026 vs Q2 2025" compares periods of one company.
        compare_words = re.search(r"\b(?:compare|vs|versus)\b", normalized) and not (
            len(companies) == 1 and len(parse_named_periods(normalized)) >= 2
        )
        if len(companies) >= 2 or compare_words:
            if metric == "unknown" and len(companies) >= 2 and _names_only(query, mentions):
                metric = OVERVIEW_PLAN
            return SimpleNamespace(
                intent=Intent.COMPARE, companies=companies, metric=metric, notes=notes
            )
        company = companies[0] if companies else _company_from_query(normalized)
        return SimpleNamespace(intent=Intent.LOOKUP, company=company, metric=metric, notes=notes)


# Wording that names no metric but implies some (see ``implied_metrics``). The
# overview fallback for short messages is left out: "chart it" is not a request
# for revenue and margins.
_IMPLIED_WORDING = re.compile(
    r"\b(?:profitab|bigger|larger|biggest|largest|grow(?:ing|n|th)?\b|grew\b)", re.IGNORECASE
)

_COMPARE_FILLER = frozenset(
    """
    compare comparing comparison and vs versus against with to between the how do does
    stack up side by
    """.split()  # noqa: SIM905
)


def _names_only(query: str, mentions: list[CompanyMention]) -> bool:
    """Whether a question is companies and compare words alone ("Compare Nvidia and AMD")."""
    named = {word for mention in mentions for word in normalize(mention.typed).split()}
    return all(word in named or word in _COMPARE_FILLER for word in normalize(query).split())


_WHICH_OF_TWO = re.compile(r"\b(?:which (?:one|is|of)|both|them|compared?|vs|versus)\b")


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
    sort = _SORT_BY.match(normalized.strip(" .?!"))
    if sort is not None and spec.companies and not companies:
        # "sort by revenue": order the companies on screen, largest first.
        wanted = metric if metric in ALLOWED_METRICS else None
        return SpecPatch(
            mode="extend",
            add_metrics=(wanted,) if wanted and wanted not in spec.metrics else (),
            add_operations=("order_by_metric",),
        )
    if _RANK_WORDS.search(normalized) or _WHICH_HIGHEST.search(normalized):
        # "largest pharma companies by net income" is a new ranking, not an edit.
        return None
    if (
        not companies
        and metric == "unknown"
        and spec.companies
        and _COMPARE_THEM.fullmatch(normalized.strip(" .?!"))
    ):
        earlier = spec.earlier_companies if len(spec.companies) == 1 else ()
        return SpecPatch(mode="extend", add_companies=earlier)
    if companies and metric in ALLOWED_METRICS and spec.companies and _LEADING_AND.search(
        normalized
    ):
        # "and msft revenue" after Apple's revenue: Microsoft joins the table.
        return SpecPatch(
            mode="extend",
            add_companies=tuple(companies),
            add_metrics=(metric,) if metric not in spec.metrics else (),
        )
    if companies and metric == "unknown" and spec.companies:
        if _ADD_WORDING.search(normalized) or _COMPARE_TO_WORDING.search(normalized):
            return SpecPatch(mode="extend", add_companies=tuple(companies))
        if _SWAP_WORDING.search(normalized) or len(normalized.split()) <= 2:
            return SpecPatch(
                mode="extend",
                remove_companies=tuple(company.query for company in spec.companies),
                add_companies=tuple(companies),
            )
        return None
    if (
        not companies
        and metric not in ALLOWED_METRICS
        and (spec.companies or spec.constituents is not None)
        and _IMPLIED_WORDING.search(normalized)
    ):
        # "which one is more profitable?" asks the current analysis a new question.
        earlier = (
            spec.earlier_companies
            if len(spec.companies) == 1 and _WHICH_OF_TWO.search(normalized)
            else ()
        )
        # After "what about AMD?", "which one" means Nvidia and AMD.
        return SpecPatch(
            mode="extend", add_companies=earlier, add_metrics=implied_metrics(normalized)
        )
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
