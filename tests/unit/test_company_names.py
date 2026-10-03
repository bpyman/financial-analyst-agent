"""Company names: one reading for the planner and for spec resolution.

A name resolves the same way wherever it is read: in the question, or in a
company field a planner filled in ("Goldman Sachs", "Merck & Co.", "$TMO").
A name that is also an everyday word ("Target", "Block", "Gap") is a company
only where the question uses it as one. A name several companies share
("Lincoln") is asked about, not guessed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from financial_analyst_agent.contracts import RendererKind, Runtime
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.domain.errors import AmbiguousCompanyError
from financial_analyst_agent.issuer_index import _everyday_words, _ordinary
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.rules_planner import DemoCompleter, issuer_index
from financial_analyst_agent.thread_store import LocalThreadStore
from financial_analyst_agent.universe import load_universe_snapshot


def _ranking() -> SnapshotRanking:
    return SnapshotRanking.from_path(None, issuer_index())


def _found(question: str) -> list[str]:
    return [mention.query for mention in issuer_index().find(question)]


@pytest.mark.parametrize(
    ("company", "ticker"),
    [
        ("Goldman Sachs", "GS"),
        ("The Goldman Sachs Group", "GS"),
        ("Home Depot", "HD"),
        ("Lilly", "LLY"),
        ("Eli Lilly & Company", "LLY"),
        ("BofA", "BAC"),
        ("Johnson and Johnson", "JNJ"),
        ("Merck and Co", "MRK"),
        ("Danaher's", "DHR"),
        ("Oracle's", "ORCL"),
        ("$TMO", "TMO"),
        ("DHR.", "DHR"),
        ("Procter & Gamble", "PG"),
        ("Facebook", "META"),
        ("Coca-Cola", "KO"),
        ("JP Morgan", "JPM"),
        ("NVIDIA Corp.", "NVDA"),
        ("Broadcom Inc.'s", "AVGO"),
        ("Cisco Systems'", "CSCO"),
        ("Take-Two", "TTWO"),
        ("Target", "TGT"),
        ("Block", "XYZ"),
    ],
)
def test_a_company_field_resolves_as_the_planner_reads_it(company: str, ticker: str) -> None:
    assert _ranking().lookup_member(company).ticker == ticker


def test_a_ranking_without_an_index_builds_one_from_its_snapshot() -> None:
    ranking = SnapshotRanking(load_universe_snapshot(None))

    assert ranking.lookup_member("Goldman Sachs").ticker == "GS"


def test_a_shared_name_offers_the_largest_members() -> None:
    with pytest.raises(AmbiguousCompanyError) as raised:
        _ranking().lookup_member("Lincoln")

    tickers = [match["ticker"] for match in raised.value.details["matches"]]
    assert tickers[:2] == ["LECO", "LNC"]
    assert len(tickers) <= 4


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("What is Target's revenue?", ["TGT"]),
        ("target revenue last quarter", ["TGT"]),
        ("compare target and walmart revenue", ["TGT", "WMT"]),
        ("Walmart, Target and Costco revenue", ["WMT", "TGT", "COST"]),
        ("how did target do last quarter", ["TGT"]),
        ("revenue for target last quarter", ["TGT"]),
        ("Is Target growing faster than Walmart?", ["TGT", "WMT"]),
        ("what about block?", ["XYZ"]),
        ("Gap revenue", ["GAP"]),
        ("match group revenue", ["MTCH"]),
        ("TARGET REVENUE", ["TGT"]),
        ("Target", ["TGT"]),
    ],
)
def test_an_everyday_word_used_as_a_company_is_one(question: str, companies: list[str]) -> None:
    assert _found(question) == companies


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("Nvidia's target margin", ["NVDA"]),
        ("Nvidia target margin", ["NVDA"]),
        ("What is the target margin for Nvidia?", ["NVDA"]),
        ("Is Nvidia hitting its target?", ["NVDA"]),
        ("price target for Nvidia", ["NVDA"]),
        ("a target of 30% for Apple", ["Apple"]),
        ("what's the gap between Apple and Microsoft revenue", ["Apple", "Microsoft"]),
        ("show me apple revenue here", ["Apple"]),
        ("take a look at Apple revenue", ["Apple"]),
        ("Ask the oracle: what's Gilead's net margin?", ["GILD"]),
        ("Any intel on AMD's R&D spending?", ["AMD"]),
    ],
)
def test_an_everyday_word_used_as_a_word_is_not_a_company(
    question: str, companies: list[str]
) -> None:
    assert _found(question) == companies


def _one_word_names(*, everyday: bool) -> list[tuple[str, str]]:
    index = issuer_index()
    return sorted(
        (phrase, ticker)
        for phrase, ticker in index.phrases.items()
        if " " not in phrase
        and phrase.isalpha()
        and _ordinary(phrase)
        and (phrase in _everyday_words()) == everyday
        and ticker != "NVDA"
    )


@pytest.mark.parametrize(("word", "ticker"), _one_word_names(everyday=True))
def test_every_everyday_word_name_reads_both_ways(word: str, ticker: str) -> None:
    assert ticker in _found(f"What was {word.title()}'s revenue last quarter?")
    assert ticker in _found(f"compare {word} and Nvidia revenue")
    assert ticker not in _found(f"Nvidia's {word} margin")
    assert ticker not in _found(f"What is the {word} for Nvidia?")


@pytest.mark.parametrize(("word", "ticker"), _one_word_names(everyday=False))
def test_every_capitalised_name_is_a_company_unless_plainly_a_word(word: str, ticker: str) -> None:
    assert ticker in _found(f"{word} revenue last quarter")
    assert ticker in _found(f"is {word} profitable")
    assert ticker not in _found(f"Ask the {word}: what's Nvidia's revenue?")


class _Facts:
    def __init__(self) -> None:
        self.companies: list[str] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return (date(2026, 6, 30), date(2026, 3, 31))[:limit]

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        self.companies.append(company)
        return SimpleNamespace(
            company_name="Lincoln National Corporation",
            ticker="LNC",
            cik="0000059558",
            metric=metric,
            value=Decimal("4542000000"),
            currency="USD",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            filed_date=date(2026, 8, 1),
            form="10-Q",
            accession_number="0000059558-26-000001",
            taxonomy="us-gaap",
            concept="Revenues",
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


@pytest.mark.parametrize("answer", ["2", "LNC", "Lincoln National", "the national one"])
def test_a_shared_name_asks_which_company_then_answers(tmp_path: Path, answer: str) -> None:
    facts = _Facts()
    runtime = Runtime(
        completer=DemoCompleter(issuer_index()),
        facts=facts,  # type: ignore[arg-type]
        ranking=_ranking(),
    )
    store = LocalThreadStore(tmp_path)

    asked = run_conversation_turn("t1", "Lincoln revenue", runtime, store=store).result

    assert asked.renderer is RendererKind.CLARIFY
    assert asked.clarify_kind == "ambiguous_company"
    assert asked.clarify_subject == "Lincoln"
    assert asked.candidates[:2] == ("LECO", "LNC")
    assert asked.candidate_labels[1] == "Lincoln National Corporation (LNC)"
    assert facts.companies == []

    answered = run_conversation_turn("t1", answer, runtime, store=store).result

    assert answered.renderer is not RendererKind.CLARIFY
    assert [row.ticker for row in answered.table_rows] == ["LNC"]
    assert {company for company in facts.companies} == {"LNC"}
