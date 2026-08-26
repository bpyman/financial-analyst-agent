"""Structured workflows run through the parent graph (migration step 1).

Asserts the public graph entry returns the same TurnResult shape as today's
workflows. Does not assert node names, channels, or LangGraph internals.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH


class _LookupFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        assert company == "Google"
        assert metric == "net_income"
        return SimpleNamespace(
            company_name="Alphabet Inc.",
            ticker="GOOG",
            cik="0001652044",
            metric="net_income",
            value=Decimal("62578000000"),
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            form="10-Q",
            accession_number="0001652044-26-000048",
            taxonomy="us-gaap",
            concept="NetIncomeLoss",
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


class _CompareFacts:
    def get_financials(self, company: str, metric: str) -> SimpleNamespace:
        values = {
            ("Microsoft", "operating_income"): Decimal("100"),
            ("Microsoft", "revenue"): Decimal("400"),
            ("Google", "operating_income"): Decimal("50"),
            ("Google", "revenue"): Decimal("200"),
        }
        value = values[(company, metric)]
        return SimpleNamespace(
            company_name=company,
            ticker="MSFT" if company == "Microsoft" else "GOOG",
            cik="0000789019" if company == "Microsoft" else "0001652044",
            metric=metric,
            value=value,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            form="10-Q",
            accession_number="acc",
            taxonomy="us-gaap",
            concept=metric,
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


class _SilentCompleter:
    def complete(self, query: str) -> SimpleNamespace:
        raise AssertionError("structured graph entry must not re-plan")


def _runtime(*, facts: object, ranking: object | None = None) -> object:
    from financial_analyst_agent.contracts import Runtime

    return Runtime(
        completer=_SilentCompleter(),
        facts=facts,  # type: ignore[arg-type]
        ranking=ranking,  # type: ignore[arg-type]
    )


def test_run_structured_turn_lookup_returns_table() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult
    from financial_analyst_agent.graph import run_structured_turn

    plan = SimpleNamespace(intent=Intent.LOOKUP, company="Google", metric="net_income")
    result = run_structured_turn(plan, _runtime(facts=_LookupFacts()))  # type: ignore[arg-type]

    assert type(result).__name__ == TurnResult.__name__
    assert result.intent == Intent.LOOKUP
    assert result.renderer == RendererKind.TABLE
    assert result.table_rows[0].value == Decimal("62578000000")
    assert result.tool_traces[0].tool == "get_financials"


def test_run_structured_turn_compare_returns_table() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.graph import run_structured_turn

    plan = SimpleNamespace(
        intent=Intent.COMPARE,
        companies=["Microsoft", "Google"],
        metric="operating_margin",
    )
    result = run_structured_turn(plan, _runtime(facts=_CompareFacts()))  # type: ignore[arg-type]

    assert result.intent == Intent.COMPARE
    assert result.renderer == RendererKind.TABLE
    assert len(result.table_rows) == 2
    assert result.tool_traces[0].tool == "compare_metrics"


def test_run_structured_turn_rank_returns_table() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.graph import run_structured_turn

    ranking = SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH)
    plan = SimpleNamespace(intent=Intent.RANK, industry="healthcare", limit=3)
    result = run_structured_turn(
        plan,
        _runtime(facts=_LookupFacts(), ranking=ranking),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.RANK
    assert result.renderer == RendererKind.TABLE
    assert len(result.table_rows) == 3
    assert result.tool_traces[0].tool == "rank_companies"


def test_run_structured_turn_rank_and_lookup_returns_table() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.graph import run_structured_turn

    ranking = SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH)
    plan = SimpleNamespace(
        intent=Intent.RANK_AND_LOOKUP,
        industry="healthcare",
        limit=2,
        metric="market_cap",
    )
    result = run_structured_turn(
        plan,
        _runtime(facts=_LookupFacts(), ranking=ranking),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.RANK_AND_LOOKUP
    assert result.renderer == RendererKind.TABLE
    assert len(result.table_rows) == 2
    assert result.tool_traces[0].tool == "rank_companies"
