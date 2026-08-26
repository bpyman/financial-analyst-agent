"""Follow-ups from analyst wording, even when the completer still emits a Plan.

Live OpenAI currently lifts closed intents as replace patches. These cases
assert the conversation seam still extends the current analysis.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH


class _PeriodFacts:
    Q2 = date(2025, 6, 30)
    Q1 = date(2025, 3, 31)
    Q4 = date(2024, 12, 31)
    Q3 = date(2024, 9, 30)
    Q2_PRIOR = date(2024, 6, 30)
    Q1_PRIOR = date(2024, 3, 31)
    Q4_OLDER = date(2023, 12, 31)
    Q3_OLDER = date(2023, 9, 30)

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return (
            self.Q2,
            self.Q1,
            self.Q4,
            self.Q3,
            self.Q2_PRIOR,
            self.Q1_PRIOR,
            self.Q4_OLDER,
            self.Q3_OLDER,
        )[:limit]

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        end = report_date or self.Q2
        return SimpleNamespace(
            company_name=company,
            ticker="GOOG" if "Google" in company or "Alphabet" in company else "MSFT",
            cik="0001652044" if "Google" in company or "Alphabet" in company else "0000789019",
            metric=metric,
            value=Decimal("100"),
            currency="USD",
            start_date=date(end.year, end.month, 1),
            end_date=end,
            form="10-Q",
            accession_number="acc",
            taxonomy="us-gaap",
            concept="Revenues",
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


class _RecordingCompleter:
    def __init__(self, plans: list[object]) -> None:
        self.plans = list(plans)
        self.calls: list[tuple[str, object]] = []

    def complete(self, query: str, current_spec: object = None) -> object:
        self.calls.append((query, current_spec))
        return self.plans.pop(0)


def _lookup_plan(company: str, metric: str) -> SimpleNamespace:
    from financial_analyst_agent.contracts import Intent

    return SimpleNamespace(
        intent=Intent.LOOKUP,
        company=company,
        companies=[],
        metric=metric,
        industry=None,
        limit=10,
        topic=None,
    )


def _runtime(completer: object, facts: object | None = None):
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.ranking import SnapshotRanking

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=(facts or _PeriodFacts()),  # type: ignore[arg-type]
        ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
    )


def test_add_company_wording_extends_even_when_planner_emits_lookup(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Google", "net_income"),
            _lookup_plan("Apple", "unknown"),
        ]
    )
    runtime = _runtime(completer)
    run_conversation_turn(
        "t1",
        "What was Google's latest quarterly net income?",
        runtime,
        store=store,
    )
    turn = run_conversation_turn("t1", "add Apple", runtime, store=store)

    assert completer.calls[1][1] is not None
    names = [company.query for company in turn.analysis_spec.companies]  # type: ignore[union-attr]
    assert "Google" in names
    assert any("Apple" in name for name in names)
    assert turn.analysis_spec.metrics == ("net_income",)  # type: ignore[union-attr]
    assert turn.result.intent.value == "compare"


def test_standalone_lookup_replaces_even_when_planner_extends(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Microsoft", "revenue"),
            _lookup_plan("Apple", "revenue"),
            SpecPatch(
                mode="extend",
                add_companies=("Tesla",),
                add_metrics=("net_income",),
            ),
        ]
    )
    runtime = _runtime(completer)
    run_conversation_turn(
        "t1", "What was Microsoft's latest quarterly revenue?", runtime, store=store
    )
    swapped = run_conversation_turn(
        "t1", "use Apple instead of Microsoft", runtime, store=store
    )
    assert [c.query for c in swapped.analysis_spec.companies] == ["Apple"]  # type: ignore[union-attr]
    assert swapped.analysis_spec.metrics == ("revenue",)  # type: ignore[union-attr]

    turn = run_conversation_turn(
        "t1",
        "What was Tesla's latest quarterly net income?",
        runtime,
        store=store,
    )
    names = [company.query for company in turn.analysis_spec.companies]  # type: ignore[union-attr]
    assert names == ["Tesla"]
    assert turn.analysis_spec.metrics == ("net_income",)  # type: ignore[union-attr]
    assert turn.result.intent.value == "lookup"


def test_standalone_period_question_replaces_instead_of_widening_window(
    tmp_path: Path,
) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Google", "revenue"),
            SpecPatch(
                mode="replace",
                add_companies=("Tesla",),
                add_metrics=("revenue",),
                set_periods=PeriodSelection(kind="last_n_quarters", count=4),
            ),
        ]
    )
    runtime = _runtime(completer)
    run_conversation_turn("t1", "Google latest quarterly revenue", runtime, store=store)
    turn = run_conversation_turn(
        "t1",
        "What was Tesla's revenue over the last four quarters?",
        runtime,
        store=store,
    )
    names = [company.query for company in turn.analysis_spec.companies]  # type: ignore[union-attr]
    assert names == ["Tesla"]
    assert turn.analysis_spec.metrics == ("revenue",)  # type: ignore[union-attr]
    assert turn.analysis_spec.periods.kind == "last_n_quarters"  # type: ignore[union-attr]
    assert turn.analysis_spec.periods.count == 4  # type: ignore[union-attr]


def test_metric_swap_does_not_invent_a_company(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Google", "revenue"),
            _lookup_plan("Google", "net_income"),
        ]
    )
    runtime = _runtime(completer)
    run_conversation_turn("t1", "Google latest quarterly revenue", runtime, store=store)
    turn = run_conversation_turn(
        "t1", "use net income instead of revenue", runtime, store=store
    )
    assert [c.query for c in turn.analysis_spec.companies] == ["Google"]  # type: ignore[union-attr]
    assert turn.analysis_spec.metrics == ("net_income",)  # type: ignore[union-attr]


def test_compare_to_issuer_extends_current_analysis(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Google", "revenue"),
            SpecPatch(mode="extend", add_companies=("Apple",)),
        ]
    )
    runtime = _runtime(completer)
    run_conversation_turn("t1", "Google latest quarterly revenue", runtime, store=store)
    turn = run_conversation_turn("t1", "compare to Apple", runtime, store=store)
    names = [company.query for company in turn.analysis_spec.companies]  # type: ignore[union-attr]
    assert "Google" in names
    assert any("Apple" in name for name in names)
    assert turn.analysis_spec.metrics == ("revenue",)  # type: ignore[union-attr]
    assert turn.result.intent.value == "compare"


def test_add_multiple_companies_and_unknown_metric_phrase(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    runtime = _runtime(
        _RecordingCompleter(
            [
                _lookup_plan("Google", "net_income"),
                SpecPatch(mode="extend", add_companies=("Apple",)),
            ]
        )
    )
    run_conversation_turn(
        "t1", "What was Google's latest quarterly net income?", runtime, store=store
    )
    added = run_conversation_turn(
        "t1", "add Apple and Microsoft", runtime, store=store
    )
    names = [company.query for company in added.analysis_spec.companies]  # type: ignore[union-attr]
    assert "Google" in names
    assert any("Apple" in name for name in names)
    assert any("Microsoft" in name for name in names)

    refused = run_conversation_turn(
        "t2",
        "What was Google's latest quarterly net income?",
        _runtime(_RecordingCompleter([_lookup_plan("Google", "net_income")])),
        store=store,
    )
    assert refused.analysis_spec is not None
    ebitda = run_conversation_turn(
        "t2",
        "add EBITDA",
        _runtime(
            _RecordingCompleter(
                [SpecPatch(mode="extend", add_metrics=("ebitda",))]
            )
        ),
        store=store,
    )
    assert ebitda.result.renderer is RendererKind.REFUSE
    assert "ebitda" in (ebitda.result.message or "").casefold()


def test_unmaterialized_window_refuses_instead_of_latest_quarter(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _NoDates:
        def get_financials(self, company: str, metric: str, **_kwargs: object) -> object:
            raise AssertionError("must not fall back to latest-quarter lookup")

        def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple:
            return ()

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Google", "revenue"),
            SpecPatch(
                mode="extend",
                set_periods=PeriodSelection(kind="last_n_quarters", count=4),
            ),
        ]
    )
    runtime = _runtime(completer, facts=_NoDates())
    run_conversation_turn(
        "t1",
        "Google latest quarterly revenue",
        _runtime(_RecordingCompleter([_lookup_plan("Google", "revenue")])),
        store=store,
    )
    turn = run_conversation_turn(
        "t1", "make that the last four quarters", runtime, store=store
    )
    assert turn.result.renderer is RendererKind.REFUSE
    assert turn.result.tool_traces == []


def test_remove_profit_clarification_drops_the_metric(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Google", "revenue"),
            _lookup_plan("Google", "net_income"),
            _lookup_plan("Google", "revenue"),
        ]
    )
    runtime = _runtime(completer)
    run_conversation_turn("t1", "Google latest quarterly revenue", runtime, store=store)
    run_conversation_turn("t1", "now add net income", runtime, store=store)
    clarified = run_conversation_turn("t1", "remove profit", runtime, store=store)
    assert clarified.result.renderer.value == "clarify"
    turn = run_conversation_turn("t1", "net_income", runtime, store=store)
    assert "net_income" not in turn.analysis_spec.metrics  # type: ignore[union-attr]
    assert turn.analysis_spec.metrics == ("revenue",)  # type: ignore[union-attr]


def test_wording_overrides_planner_period_count(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Google", "revenue"),
            SpecPatch(
                mode="extend",
                set_periods=PeriodSelection(kind="last_n_quarters", count=4),
            ),
        ]
    )
    runtime = _runtime(completer)
    run_conversation_turn("t1", "Google latest quarterly revenue", runtime, store=store)
    turn = run_conversation_turn("t1", "last six quarters", runtime, store=store)
    assert turn.analysis_spec.periods.count == 6  # type: ignore[union-attr]


def test_add_metric_and_last_four_quarters_from_wording(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    completer = _RecordingCompleter(
        [
            _lookup_plan("Google", "revenue"),
            _lookup_plan("Google", "operating_margin"),
            _lookup_plan("Google", "revenue"),
        ]
    )
    runtime = _runtime(completer, facts=_PeriodFacts())
    run_conversation_turn("t1", "Google latest quarterly revenue", runtime, store=store)
    added = run_conversation_turn("t1", "now add operating margin", runtime, store=store)
    assert added.analysis_spec.metrics == ("revenue", "operating_margin")  # type: ignore[union-attr]

    windowed = run_conversation_turn(
        "t1", "make that the last four quarters", runtime, store=store
    )
    assert windowed.analysis_spec.periods.kind == "last_n_quarters"  # type: ignore[union-attr]
    assert windowed.analysis_spec.periods.count == 4  # type: ignore[union-attr]
    assert len(windowed.analysis_spec.periods.report_dates) == 4  # type: ignore[union-attr]
    assert len(windowed.result.table_rows) >= 8


def test_openai_follow_up_schema_includes_current_spec() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        ResolvedCompany,
    )
    from financial_analyst_agent.planner import FollowUpPlan, OpenAIStructuredCompleter, SpecPatch

    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(cik="0001652044", name="Alphabet", ticker="GOOG", query="Google"),
        ),
        metrics=("net_income",),
        periods=PeriodSelection(),
    )
    parsed = FollowUpPlan.model_validate(
        {
            "intent": "spec_patch",
            "mode": "extend",
            "add_companies": ["Apple"],
        }
    )
    client_calls: list[dict] = []

    class _Client:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self.parse))

        def parse(self, **kwargs: object) -> object:
            client_calls.append(kwargs)
            message = SimpleNamespace(parsed=parsed, refusal=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    proposal = OpenAIStructuredCompleter(_Client(), "gpt-test").complete(
        "add Apple", current_spec=spec
    )
    assert isinstance(proposal, SpecPatch)
    assert proposal.mode == "extend"
    assert proposal.add_companies == ("Apple",)
    contents = " ".join(str(item["content"]) for item in client_calls[0]["messages"])
    assert "net_income" in contents
    assert "Google" in contents or "Alphabet" in contents
    assert client_calls[0]["response_format"] is FollowUpPlan
