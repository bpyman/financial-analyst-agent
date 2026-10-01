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


@pytest.mark.parametrize(
    ("title", "tickers", "operating"),
    [
        ("MICROSOFT CORP", ["MSFT"], True),
        ("CITIGROUP INC", ["C", "C-PN"], True),
        ("ACME CAPITAL TRUST II 7.875% NOTES", ["ACMA"], False),
        ("ACME FINANCE CO", ["ACM-PA", "ACM-PB"], False),
    ],
)
def test_a_name_outside_the_freeze_is_judged_by_its_sec_identity(
    title: str, tickers: list[str], operating: bool
) -> None:
    # ADR 0002: ticker suffix and listing-title tokens, not only the CIK list.
    from financial_analyst_agent.universe import sec_identity_is_operating

    assert sec_identity_is_operating("0009999999", title, tickers) is operating


def test_an_ineligible_issuer_is_a_typed_miss_in_a_comparison() -> None:
    # ADR 0002: the row that failed the rule says so; the other row stays.
    from financial_analyst_agent.contracts import NOT_OPERATING_COMPANY
    from financial_analyst_agent.domain.errors import IneligibleIssuerError
    from financial_analyst_agent.turn import compare_metrics

    class _Facts:
        def get_financials(self, company: str, metric: str, **_: object) -> object:
            raise IneligibleIssuerError("ARES CAPITAL CORP is not an operating company")

    [row] = compare_metrics(_Facts(), ["ARCC"], "revenue")  # type: ignore[arg-type]

    assert row.reason == NOT_OPERATING_COMPANY
    assert row.value is None
