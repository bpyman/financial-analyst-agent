"""Find the companies a question names, from a snapshot's names and tickers.

The rules planner reads questions without a model, so it needs to know which
words are companies: "Costco", "Coca-Cola", "$NFLX", or a misspelt "Microsft".
The index is built once per snapshot file and answers in a dictionary lookup
per word n-gram; typo matching runs only when nothing matched exactly.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from financial_analyst_agent.universe import UniverseCompany

# Legal-form and filler words a company name drops in speech.
_NAME_SUFFIXES = frozenset(
    {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "companies",
        "ltd",
        "limited",
        "plc",
        "llc",
        "lp",
        "l.p",
        "sa",
        "nv",
        "ag",
        "se",
        "holdings",
        "holding",
        "group",
        "the",
        "class",
        "com",
        "new",
        "de",
    }
)
# First words that are not a company on their own ("General" Motors,
# "American" Express), plus words a question uses for something else.
_GENERIC_WORDS = frozenset(
    """
    a about above after all also american an and any are as at bank banks be best big
    biggest by can capital central century citizens common compare could data did digital
    do does doing east eastern energy equity federal financial first for from general
    global good great growth had has have health healthcare home how i in income industries
    international is it its just last latest life margin market me medical micro more most
    much my national net new north northern of on one or our pacific people profit public
    quarter quarters real restaurant restaurants revenue royal sales service services show
    so south southern stock stocks telecom than that the their them then there these they
    this to top total trust
    united universal us value vs was were west western what when which who why will with
    world would year you your
    """.split()  # noqa: SIM905
)
# Uppercase words in a question that are not tickers.
_NOT_TICKERS = frozenset(
    {
        "A",
        "I",
        "AI",
        "CEO",
        "CFO",
        "EPS",
        "FCF",
        "OCF",
        "CY",
        "LTM",
        "ROE",
        "ROA",
        "US",
        "USA",
        "SEC",
        "FY",
        "YOY",
        "QOQ",
        "TTM",
        "GAAP",
        "EBIT",
        "EBITDA",
        "IPO",
        "ETF",
        "OK",
        "VS",
        "AND",
        "OR",
        "THE",
        "TOP",
        "MD",
        "API",
        "GDP",
        "R",
        "D",
        "Q",
    }
)
# Names people use that no listing title contains, by the ticker they mean.
# Applied only when that ticker is in the snapshot.
_NICKNAMES: tuple[tuple[str, str], ...] = (
    ("pepsi", "PEP"),
    ("coke", "KO"),
    ("facebook", "META"),
    ("p&g", "PG"),
    ("bofa", "BAC"),
    ("disney", "DIS"),
    ("ibm", "IBM"),
    ("honeywell", "HON"),
    ("3m", "MMM"),
    ("comcast", "CMCSA"),
    ("amex", "AXP"),
    ("exxonmobil", "XOM"),
    ("berkshire", "BRK-B"),
    ("citi", "C"),
    ("chase", "JPM"),
    ("raytheon", "RTX"),
    ("ups", "UPS"),
    ("att", "T"),
    ("cvs", "CVS"),
    ("hp", "HPQ"),
    ("schwab", "SCHW"),
    ("capital one", "COF"),
)
_MAX_NGRAM = 5
_FIRST_WORD_ALIAS_RANK = 1500
_TYPO_CUTOFF = 0.84
_TYPO_MIN_LENGTH = 5


def normalize(text: str) -> str:
    """Casefold, drop possessives, and keep only word characters and ``&``."""
    text = text.casefold().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    text = re.sub(r"[^\w&]+", " ", text)
    return " ".join(text.split())


def _core_name(name: str) -> str:
    words = normalize(name).split()
    while words and words[-1] in _NAME_SUFFIXES:
        words.pop()
    while words and words[0] == "the":
        words.pop(0)
    return " ".join(words)


@dataclass(frozen=True)
class CompanyMention:
    """One company named in a question, in the order it was named."""

    query: str
    start: int
    typed: str
    corrected: bool = False


@dataclass
class IssuerIndex:
    """Phrases that name a company, mapped to the query the resolver takes."""

    phrases: dict[str, str] = field(default_factory=dict)
    tickers: dict[str, str] = field(default_factory=dict)
    display_names: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        companies: Sequence[UniverseCompany],
        aliases: Iterable[tuple[str, str]] = (),
    ) -> IssuerIndex:
        index = cls()
        for phrase, query in aliases:
            index.phrases.setdefault(normalize(phrase), query)
        listed = {company.ticker.upper() for company in companies}
        for phrase, ticker in _NICKNAMES:
            if ticker in listed:
                index.phrases.setdefault(phrase, ticker)
        ranked = sorted(companies, key=lambda company: company.market_cap, reverse=True)
        first_words: dict[str, list[str]] = {}
        for rank, company in enumerate(ranked):
            ticker = company.ticker.upper()
            index.tickers.setdefault(ticker, ticker)
            index.display_names.setdefault(ticker, company.name)
            core = _core_name(company.name)
            if not core or (" " not in core and (core in _GENERIC_WORDS or len(core) < 3)):
                # "Southern Company" is not "southern"; "Target" still is "target".
                continue
            index.phrases.setdefault(core, ticker)
            # "Lowe's" is also typed "Lowes".
            joined = _core_name(company.name.replace("'", "").replace("’", ""))
            if joined != core:
                index.phrases.setdefault(joined, ticker)
            if "&" in core:
                index.phrases.setdefault(core.replace("&", "and"), ticker)
            words = core.split()
            if (
                rank < _FIRST_WORD_ALIAS_RANK
                and len(words) > 1
                and len(words[0]) >= 4
                and words[0] not in _GENERIC_WORDS
            ):
                first_words.setdefault(words[0], []).append(ticker)
        for word, owners in first_words.items():
            # "Costco" for Costco Wholesale; a word two large companies share
            # ("Bank" of America and "Bank" of New York) names neither.
            if len(owners) == 1:
                index.phrases.setdefault(word, owners[0])
        return index

    def find(self, question: str) -> list[CompanyMention]:
        """Companies named exactly, longest phrase first, in question order."""
        normalized = normalize(question)
        words = normalized.split()
        offsets: list[int] = []
        position = 0
        for word in words:
            offsets.append(position)
            position += len(word) + 1
        taken = [False] * len(words)
        found: dict[str, CompanyMention] = {}
        for size in range(min(_MAX_NGRAM, len(words)), 0, -1):
            for start in range(len(words) - size + 1):
                if any(taken[start : start + size]):
                    continue
                phrase = " ".join(words[start : start + size])
                query = self.phrases.get(phrase)
                if query is None:
                    continue
                for slot in range(start, start + size):
                    taken[slot] = True
                if query not in found:
                    found[query] = CompanyMention(query, offsets[start], phrase)
        for match in re.finditer(r"(?<![\w&])\$?([A-Za-z]{1,5})(?![\w&])", question):
            raw = match.group(1)
            dollar = match.group(0).startswith("$")
            if not dollar and (raw != raw.upper() or raw in _NOT_TICKERS):
                continue
            if raw.casefold() in self.phrases:
                # "AAPL" is also an alias phrase; the phrase pass named it once.
                continue
            query = self.tickers.get(raw.upper())
            if query is not None and query not in found:
                found[query] = CompanyMention(query, _char_to_word_offset(question, match), raw)
        return sorted(found.values(), key=lambda mention: mention.start)

    def correct(
        self, question: str, *, ignore: frozenset[str] = frozenset()
    ) -> list[CompanyMention]:
        """Close misspellings of a company name ("Microsft", "Nvida")."""
        candidates = [phrase for phrase in self.phrases if len(phrase) >= _TYPO_MIN_LENGTH]
        mentions: list[CompanyMention] = []
        position = 0
        for word in normalize(question).split():
            start = position
            position += len(word) + 1
            if (
                len(word) < _TYPO_MIN_LENGTH
                or not word.isalpha()
                or word in _GENERIC_WORDS
                or word in ignore
                or word in self.phrases
            ):
                continue
            close = difflib.get_close_matches(word, candidates, n=1, cutoff=_TYPO_CUTOFF)
            if close and close[0][0] == word[0]:
                query = self.phrases[close[0]]
                if all(mention.query != query for mention in mentions):
                    mentions.append(CompanyMention(query, start, word, corrected=True))
        return mentions

    def display_name(self, query: str) -> str:
        return self.display_names.get(query.upper(), query)


def _char_to_word_offset(question: str, match: re.Match[str]) -> int:
    # Mentions order by position in the normalized question; the raw offset is
    # close enough to keep tickers in the order they were typed.
    return len(normalize(question[: match.start()])) + (1 if match.start() else 0)
