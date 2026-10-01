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
from functools import lru_cache
from pathlib import Path

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
        "reit",
        "the",
        "class",
        "com",
        "new",
        "de",
    }
)
# A fund's name says what it is ("Blackstone Secured Lending Fund"); asked, it is dropped.
_FUND_WORDS = frozenset({"fund", "trust", "etf", "inc"})
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
    this to top total trade trust
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
        "IT",
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
        "CIK",
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
    ("general electric", "GE"),
    ("southern company", "SO"),
    ("us bancorp", "USB"),
    ("bank of new york", "BNY"),
    ("oreilly", "ORLY"),
    ("tsmc", "TSM"),
    ("tmobile", "TMUS"),
)
# Two-word starts of a longer name that are places or words, not that company:
# "New York" Times, "Las Vegas" Sands.
_NOT_SHORT_NAMES = frozenset({"las vegas", "grupo financiero", "super group"})
# A ticker, with a share class after a dot, dash or slash ("BRK.B"). Letters
# joined to a word are not tickers: "S&P", "T-Mobile", "O'Reilly".
_TICKER = re.compile(
    r"(?<![\w&/.'’-])\$?([A-Za-z]{1,5})(?:[./-]([A-Za-z]))?(?![\w&/'’])(?![./-][A-Za-z])"
)
# Tickers that also start a metric's name: "NET income" is not Cloudflare's.
_METRIC_STARTS = {
    "NET": frozenset({"income", "margin", "loss", "losses", "sales", "profit", "debt", "interest"}),
    "CASH": frozenset({"flow", "flows"}),
}
# SEC titles end with a state or "new" marker: "CONSUMERS BANCORP INC /OH/".
_SEC_STATE = re.compile(r"\s*/[A-Za-z .]+/?\s*$")
_CIK = re.compile(r"\bcik\s*#?:?\s*(\d{1,10})\b|\b(0\d{9})\b", re.IGNORECASE)
_MAX_NGRAM = 5
_FIRST_WORD_ALIAS_RANK = 1500
_TYPO_CUTOFF = 0.84
_TYPO_MIN_LENGTH = 5
# A four-letter word is corrected only when one letter is missing ("aple").
_SHORT_TYPO_LENGTH = 4


# Groups people name as if they were one company.
_GROUPS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:the\s+)?(?:magnificent|mag)\s*(?:7|seven)\b", re.I),
        "Apple, Microsoft, Alphabet, Amazon, Nvidia, Meta and Tesla",
    ),
    (re.compile(r"\bfaang\b", re.I), "Meta, Apple, Amazon, Netflix and Alphabet"),
    (re.compile(r"\bfang\b", re.I), "Meta, Amazon, Netflix and Alphabet"),
)


def expand_groups(question: str) -> str:
    """ "Magnificent 7 revenue" → the seven companies' names, so each is looked up."""
    for pattern, names in _GROUPS:
        question = pattern.sub(names, question)
    return question


def normalize(text: str) -> str:
    """Casefold, drop possessives, and keep only word characters and ``&``."""
    text = text.casefold().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    text = re.sub(r"[^\w&]+", " ", text)
    return " ".join(text.split())


def _core_name(name: str, suffixes: frozenset[str] = _NAME_SUFFIXES) -> str:
    words = normalize(name).split()
    while words and words[-1] in suffixes:
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
    ciks: dict[str, str] = field(default_factory=dict)

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
        short_names: dict[str, list[str]] = {}
        for rank, company in enumerate(ranked):
            ticker = company.ticker.upper()
            index.tickers.setdefault(ticker, ticker)
            index.ciks.setdefault(company.cik, ticker)
            index.display_names.setdefault(ticker, company.name)
            core = _core_name(company.name)
            # "Power REIT" is named in full too, where "power" alone is not it.
            spoken = _core_name(company.name, _NAME_SUFFIXES - {"reit"})
            if spoken != core and " " in spoken:
                index.phrases.setdefault(spoken, ticker)
            if not core or (" " not in core and (core in _GENERIC_WORDS or len(core) < 3)):
                # "Southern Company" is not "southern"; "Target" still is "target".
                continue
            if " " not in core and rank >= _FIRST_WORD_ALIAS_RANK and core in _common_words():
                # A small listing does not own an everyday word: "power" is not Power REIT.
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
            if (
                rank < _FIRST_WORD_ALIAS_RANK
                and len(words) > 2
                and words[0] not in _GENERIC_WORDS
                and len(words[1]) >= 4
                and words[1] not in _GENERIC_WORDS
                and words[1] not in _NAME_SUFFIXES
            ):
                short_names.setdefault(" ".join(words[:2]), []).append(ticker)
        for word, owners in (*first_words.items(), *short_names.items()):
            # "Costco" for Costco Wholesale, "Johnson Controls" for Johnson
            # Controls International; a start two large companies share
            # ("Bank" of America and "Bank" of New York) names neither.
            if len(owners) == 1 and word not in _NOT_SHORT_NAMES:
                index.phrases.setdefault(word, owners[0])
        return index

    def add_outside(self, ticker: str, name: str) -> None:
        """A listing outside the snapshot (a fund), named so a question can reach it.

        It never takes a phrase or ticker an operating company already holds:
        "Ares" stays Ares Management, while "Ares Capital" names the fund.
        """
        query = ticker.upper()
        self.tickers.setdefault(query, query)
        self.display_names.setdefault(query, name)
        for core in {_core_name(name), _core_name(name, _NAME_SUFFIXES | _FUND_WORDS)}:
            if " " in core:
                self.phrases.setdefault(core, query)

    def add_filer(self, ticker: str, name: str, *, reserved: frozenset[str]) -> None:
        """An operating SEC filer outside the snapshot, named by its full name only.

        "Southern California Edison" and "Entergy Texas" then match whole, ahead
        of "Edison" or "Entergy" alone. A filer never takes a phrase a snapshot
        company holds, a one-word name, or a name with a ``reserved`` word in it,
        so "Apple Revenue Trust" could not capture "Apple revenue".
        """
        core = _core_name(_SEC_STATE.sub("", name))
        words = core.split()
        if len(words) < 2 or any(word in reserved or word.isdigit() for word in words):
            return
        query = ticker.upper()
        if self.phrases.setdefault(core, query) == query:
            self.display_names.setdefault(query, name)

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
        for match in _CIK.finditer(question):
            # "CIK 320193" or SEC's ten-digit "0000320193".
            query = self.ciks.get((match.group(1) or match.group(2)).zfill(10))
            if query is not None and query not in found:
                found[query] = CompanyMention(query, _char_to_word_offset(question, match), query)
        for match in _TICKER.finditer(question):
            raw, share_class = match.group(1), match.group(2)
            dollar = match.group(0).startswith("$")
            if not dollar and (raw != raw.upper() or raw in _NOT_TICKERS):
                continue
            following = question[match.end() :].split(maxsplit=1)
            if (
                not dollar
                and following
                and following[0].casefold() in _METRIC_STARTS.get(raw, frozenset())
            ):
                continue
            if share_class is not None:
                # "BRK.B" is Berkshire's B shares; "P/E" and "U.S." name no class.
                query = self.tickers.get(f"{raw}-{share_class}".upper())
            elif raw.casefold() in self.phrases:
                # "AAPL" is also an alias phrase; the phrase pass named it once.
                continue
            else:
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
            if len(word) == _SHORT_TYPO_LENGTH and word.isalpha() and word not in ignore:
                short = _one_letter_missing(word, candidates)
                if (
                    short is not None
                    and word not in _GENERIC_WORDS
                    and word not in self.phrases
                    and all(mention.query != self.phrases[short] for mention in mentions)
                ):
                    mentions.append(
                        CompanyMention(self.phrases[short], start, word, corrected=True)
                    )
                continue
            if (
                len(word) < _TYPO_MIN_LENGTH
                or not word.isalpha()
                or word in _GENERIC_WORDS
                or word in ignore
                or word in self.phrases
                or word in _common_words()
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


def _one_letter_missing(word: str, candidates: list[str]) -> str | None:
    """The one five-letter single-word name that ``word`` is missing a letter of.

    The dropped letter is inside the word: "Appl" is a prefix of several names
    (Apple, Applied Materials, AppLovin), so it is left for the resolver to refuse.
    """
    found = [
        phrase
        for phrase in candidates
        if len(phrase) == len(word) + 1
        and " " not in phrase
        and phrase[0] == word[0]
        and any(phrase[:cut] + phrase[cut + 1 :] == word for cut in range(1, len(phrase) - 1))
    ]
    return found[0] if len(found) == 1 else None


@lru_cache(maxsize=1)
def _common_words() -> frozenset[str]:
    """Words most 10-Qs use ("being", "inflation"): English, not a misspelt name.

    Built by scripts/build_common_words.py.
    """
    path = Path(__file__).parent / "data" / "common_words.txt"
    try:
        return frozenset(path.read_text(encoding="utf-8").split())
    except OSError:
        return frozenset()


def _char_to_word_offset(question: str, match: re.Match[str]) -> int:
    # Mentions order by position in the normalized question; the raw offset is
    # close enough to keep tickers in the order they were typed.
    return len(normalize(question[: match.start()])) + (1 if match.start() else 0)
