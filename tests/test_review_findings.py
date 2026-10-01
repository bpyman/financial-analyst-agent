"""Regressions for the PRD/ADR review findings, run on the recorded runtime."""

from __future__ import annotations

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind, Runtime
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.turn import run_turn


@pytest.fixture(scope="module")
def runtime() -> Runtime:
    return recorded_runtime()


def test_a_rejected_comparison_is_labelled_a_comparison(runtime: Runtime) -> None:
    # Story 32: a refusal names the analysis asked for, not a default lookup.
    result = run_turn("compare Apple and Microsoft revenue in Q3 FY2040", runtime)

    assert result.renderer is RendererKind.REFUSE
    assert result.intent is Intent.COMPARE


def test_a_cached_fact_reads_back_as_the_same_financial_fact() -> None:
    # ADR 0003: the facts port returns FinancialFact, cache hit or not.
    from datetime import date
    from decimal import Decimal

    from financial_analyst_agent.domain.enums import Metric
    from financial_analyst_agent.domain.models import FinancialFact
    from financial_analyst_agent.evidence_store import EvidenceCachedFacts, InMemoryEvidenceStore

    fact = FinancialFact(
        company_name="Microsoft Corporation",
        ticker="MSFT",
        cik="0000789019",
        metric=Metric.REVENUE,
        value=Decimal("70066000000"),
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        filed_date=date(2026, 4, 29),
        form="10-Q",
        accession_number="0000950170-26-000123",
        taxonomy="us-gaap",
        concept="Revenues",
        source_url="https://www.sec.gov/example.htm",
    )

    class _Facts:
        def get_financials(
            self, company: str, metric: str, *, report_date: date | None = None
        ) -> FinancialFact:
            return fact

    cached = EvidenceCachedFacts(_Facts(), InMemoryEvidenceStore(), prior_ids=frozenset())
    fresh = cached.get_financials("MSFT", "revenue")
    again = cached.get_financials("MSFT", "revenue")

    assert isinstance(again, FinancialFact)
    assert again == fresh == fact
