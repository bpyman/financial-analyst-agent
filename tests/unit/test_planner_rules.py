"""The rules planner reads everyday questions; the window guides and suggests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.domain.errors import UnknownIndustryError
from financial_analyst_agent.filing_change import _year_apart_quarterlies
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    RankedSet,
    ResolvedCompany,
    SpecPatch,
    apply_patch,
    resolve_spec,
)
from financial_analyst_agent.graph.spec_turn import (
    OVERVIEW_METRICS,
    _capped_ranking_notes,
    _order_by_metric,
    bind_metrics_from_message,
    bind_periods_from_message,
    plan_to_spec_patch,
)
from financial_analyst_agent.guide import guide_reply, short_name, suggest_follow_ups
from financial_analyst_agent.issuer_index import IssuerIndex
from financial_analyst_agent.presentation import present_turn
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.rules_planner import DemoCompleter, issuer_index
from financial_analyst_agent.universe import load_universe_snapshot, resolve_industry_group


def _live() -> DemoCompleter:
    return DemoCompleter(issuer_index())


def test_live_index_names_companies_by_name_ticker_and_first_word() -> None:
    index = issuer_index()

    def found(question: str) -> list[str]:
        return [mention.query for mention in index.find(question)]

    assert found("What was Costco's revenue?") == ["COST"]
    assert found("coca-cola vs pepsico net income") == ["KO", "PEP"]
    assert found("Compare $NFLX and DIS") == ["NFLX", "DIS"]
    assert found("Home Depot versus Lowes") == ["HD", "LOW"]
    # Generic first words and lowercase words are not companies.
    assert found("what are the top 5 general companies") == []
    assert found("I want AI revenue") == []


def test_misspelt_company_is_corrected_and_said() -> None:
    plan = _live().complete("microsft revenue")

    assert plan.company == "Microsoft"
    assert plan.notes == ("Showing Microsoft for “microsft”.",)


def test_a_ticker_that_is_also_an_alias_is_one_company() -> None:
    plan = DemoCompleter().complete("AAPL")

    assert plan.intent is Intent.LOOKUP


def test_which_is_bigger_compares_market_cap_and_revenue() -> None:
    plan = DemoCompleter().complete("Which is bigger, Apple or Microsoft?")
    patch = SpecPatch(mode="replace", add_companies=tuple(plan.companies), add_metrics=("unknown",))

    bound, refusal = bind_metrics_from_message(patch, "Which is bigger, Apple or Microsoft?")

    assert plan.intent is Intent.COMPARE
    assert refusal is None
    assert bound.add_metrics == ("market_cap", "revenue")


def test_a_company_on_its_own_gets_an_overview() -> None:
    patch = SpecPatch(mode="replace", add_companies=("NVDA",), add_metrics=("unknown",))

    for question in ("Nvidia", "How is Nvidia doing?", "Tell me about Nvidia"):
        bound, refusal = bind_metrics_from_message(patch, question)
        assert refusal is None
        assert bound.add_metrics == OVERVIEW_METRICS


def test_growth_wording_asks_for_year_over_year() -> None:
    patch = bind_periods_from_message(
        SpecPatch(mode="replace"), "How has Tesla's revenue changed over the last year?"
    )

    assert patch.set_periods is not None and patch.set_periods.count == 5
    assert "across_periods" in patch.add_operations


def test_rankings_read_industries_and_limits() -> None:
    plan = DemoCompleter().complete("top 5 semiconductor companies by revenue")
    banks = DemoCompleter().complete("biggest banks")

    assert (plan.intent, plan.industry, plan.limit, plan.metric) == (
        Intent.RANK_AND_LOOKUP,
        "semiconductor",
        5,
        "revenue",
    )
    assert (banks.intent, banks.industry) == (Intent.RANK, "banks")


def test_industry_words_name_industries_inside_a_sector() -> None:
    snapshot = load_universe_snapshot()

    semis = resolve_industry_group("semiconductor", snapshot)
    software = resolve_industry_group("software companies", snapshot)
    regional = resolve_industry_group("regional banks", snapshot)
    tech = resolve_industry_group("tech", snapshot)

    assert semis is not None and semis.industries == {"Semiconductors"}
    assert software is not None and software.label == "Software"
    assert regional is not None and regional.industries == {"Banks - Regional"}
    assert tech is not None and tech.sector == "Technology"
    assert resolve_industry_group("spaceships", snapshot) is None


def test_a_ranking_by_a_metric_is_ordered_by_it() -> None:
    by = _live().complete("top 5 healthcare companies by revenue")
    their = _live().complete("biggest banks and their net income")
    cap = _live().complete("top 5 banks by market cap")

    assert by.order_by_metric is True
    assert their.order_by_metric is False
    assert cap.order_by_metric is False
    assert plan_to_spec_patch(by).add_operations == ("rank", "order_by_metric")
    assert plan_to_spec_patch(their).add_operations == ("rank",)


def test_ordering_by_a_metric_reranks_the_members() -> None:
    def row(rank: int, ticker: str, value: str | None, end: date) -> TableRow:
        return TableRow(
            company_name=ticker,
            ticker=ticker,
            cik=f"000000000{rank}",
            metric="revenue",
            rank=rank,
            value=Decimal(value) if value is not None else None,
            end_date=end,
        )

    june = date(2026, 6, 30)
    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            row(1, "LLY", "22", june),
            row(2, "JNJ", "25", june),
            row(3, "XYZ", None, june),
            row(4, "UNH", "112", june),
        ],
    )

    ordered = _order_by_metric(result, "revenue")
    presented = present_turn(ordered)

    assert [(r.rank, r.ticker) for r in ordered.table_rows] == [
        (1, "UNH"),
        (2, "JNJ"),
        (3, "LLY"),
        (4, "XYZ"),
    ]
    assert ordered.ordered_by == "revenue"
    assert any(banner.startswith("Ordered by revenue.") for banner in presented.banners)
    assert presented.chart is not None
    assert presented.chart.caption.startswith("Ordered by revenue among the largest by market cap")


def test_a_ranking_lists_at_most_25_companies() -> None:
    ranking = SnapshotRanking(load_universe_snapshot())
    patch = SpecPatch(mode="replace", ranked_request=("tech", 1000))

    spec = resolve_spec(apply_patch(None, patch), ranking=ranking)

    assert spec.constituents is not None
    assert len(spec.constituents.members) == spec.constituents.limit == 25
    assert _capped_ranking_notes(patch) == [
        "A ranking lists at most 25 companies, so this shows the top 25 rather than 1000."
    ]
    assert _capped_ranking_notes(SpecPatch(mode="replace", ranked_request=("tech", 5))) == []


def test_gics_sector_names_and_common_industry_words_resolve() -> None:
    snapshot = load_universe_snapshot()

    staples = resolve_industry_group("consumer staples", snapshot)
    payments = resolve_industry_group("payments companies", snapshot)
    hotels = resolve_industry_group("hotels", snapshot)
    oil = resolve_industry_group("oil & gas", snapshot)
    healthcare = resolve_industry_group("healthcare", snapshot)

    assert staples is not None and staples.sector == "Consumer Defensive"
    assert payments is not None and payments.industries == {"Financial - Credit Services"}
    assert hotels is not None and "Travel Lodging" in hotels.industries
    assert oil is not None and len(oil.industries) > 1
    assert all(name.startswith("Oil & Gas") for name in oil.industries)
    assert healthcare is not None and healthcare.sector == "Healthcare"
    for word in ("software", "telecom", "restaurants"):
        assert resolve_industry_group(word, snapshot) is not None, word


def test_oil_and_gas_is_one_industry_in_a_ranking() -> None:
    plan = _live().complete("top 5 oil and gas companies by revenue")
    both = _live().complete("biggest banks and their net income")

    assert plan.industry == "oil & gas"
    assert both.industry == "banks"


def test_unknown_industry_names_the_snapshot_sectors() -> None:
    snapshot = load_universe_snapshot()
    with pytest.raises(UnknownIndustryError) as raised:
        SnapshotRanking(snapshot).rank_companies("spaceships", 5)
    result = TurnResult(
        intent=Intent.RANK,
        renderer=RendererKind.REFUSE,
        message=str(raised.value),
        tool_traces=[],
    )

    message = present_turn(result).message or ""

    assert "“spaceships”" in message
    assert "Healthcare" in message and "Technology" in message
    assert "finance" not in message


def _spec(*queries: str, metrics: tuple[str, ...] = ("revenue",)) -> AnalysisSpec:
    return AnalysisSpec(
        companies=tuple(
            ResolvedCompany(cik="", name=query, ticker=query, query=query) for query in queries
        ),
        metrics=metrics,
    )


def test_short_follow_ups_lean_on_the_current_analysis() -> None:
    planner = DemoCompleter()
    spec = _spec("MSFT")

    add_metric = planner.complete("and net margin", current_spec=spec)
    swap_metric = planner.complete("what about net income?", current_spec=spec)
    swap_company = planner.complete("what about Apple?", current_spec=spec)
    add_company = planner.complete("and Nvidia", current_spec=spec)

    assert add_metric == SpecPatch(mode="extend", add_metrics=("net_margin",))
    assert swap_metric == SpecPatch(
        mode="extend", add_metrics=("net_income",), remove_metrics=("revenue",)
    )
    assert swap_company == SpecPatch(
        mode="extend", remove_companies=("MSFT",), add_companies=("Apple",)
    )
    assert add_company == SpecPatch(mode="extend", add_companies=("NVDA",))


def test_which_one_after_a_swap_compares_the_two_companies() -> None:
    swapped = resolve_spec(
        apply_patch(
            _spec("NVDA"),
            SpecPatch(mode="extend", remove_companies=("NVDA",), add_companies=("AMD",)),
        )
    )
    planner = DemoCompleter()

    which = planner.complete("which one is more profitable", current_spec=swapped)
    only = planner.complete("is it profitable", current_spec=swapped)
    kept = resolve_spec(apply_patch(swapped, SpecPatch(mode="extend", add_metrics=("capex",))))

    assert swapped.earlier_companies == ("NVDA",)
    assert which == SpecPatch(
        mode="extend", add_companies=("NVDA",), add_metrics=("net_income", "net_margin")
    )
    assert only.add_companies == ()
    assert kept.earlier_companies == ("NVDA",)


def test_compare_without_a_metric_is_an_overview() -> None:
    planner = _live()

    for question in ("Compare Nvidia and AMD", "how does Nvidia stack up against AMD?"):
        plan = planner.complete(question)
        patch, refusal = bind_metrics_from_message(
            plan_to_spec_patch(plan), question, intent=plan.intent
        )
        assert refusal is None, question
        assert patch.add_metrics == OVERVIEW_METRICS, question
    unknown = planner.complete("compare apple and microsoft roa")
    _patch, refusal = bind_metrics_from_message(
        plan_to_spec_patch(unknown), "compare apple and microsoft roa", intent=unknown.intent
    )
    assert refusal is not None and refusal.renderer is RendererKind.REFUSE


def test_top_n_narrows_a_ranking_and_a_new_ranking_is_not_an_edit() -> None:
    planner = DemoCompleter()
    ranked = AnalysisSpec(
        constituents=RankedSet(industry="banks", limit=10, members=()), metrics=("revenue",)
    )

    narrowed = planner.complete("only the top 3", current_spec=ranked)
    fresh = planner.complete("largest pharma companies by net income", current_spec=ranked)

    assert narrowed == SpecPatch(mode="extend", ranked_request=("banks", 3))
    assert fresh.intent is Intent.RANK_AND_LOOKUP and fresh.industry == "pharma"


def test_filing_change_without_accessions_is_recognized_for_any_company() -> None:
    plan = DemoCompleter().complete("What changed in Apple's latest 10-Q?")

    assert plan.intent is Intent.FILING_CHANGE
    assert plan.company == "Apple"
    assert plan.section == "mda and risk_factors"


def test_year_apart_pair_prefers_the_same_quarter() -> None:
    recent = {
        "accessionNumber": ["n", "k", "p", "y"],
        "form": ["10-Q", "10-K", "10-Q", "10-Q"],
        "reportDate": ["2026-03-31", "2025-06-30", "2025-12-31", "2025-03-31"],
    }

    assert _year_apart_quarterlies(recent) == ("y", "n")


def test_guide_replies_answer_help_greetings_advice_and_why() -> None:
    index = IssuerIndex.build([], [("apple", "Apple")])
    spec = _spec("Tesla")

    hello = guide_reply("hi!", None)
    advice = guide_reply("Is Apple a good buy?", None, index)
    why = guide_reply("why?", spec)

    assert hello is not None and hello.guide and hello.suggestions
    assert advice is not None and "investment advice" in (advice.message or "")
    assert advice.suggestions[0] == "How is Apple doing?"
    assert why is not None and why.suggestions == ["What changed in Tesla's latest 10-Q?"]
    assert guide_reply("What was Apple's revenue?", None, index) is None
    assert present_turn(hello).message_tone == "info"
    assert present_turn(hello).intent_label == "Guide"


def test_suggestions_offer_a_window_a_peer_and_a_metric() -> None:
    ranking = SnapshotRanking.from_path()
    nvidia = ResolvedCompany(
        cik="0001045810", name="NVIDIA Corporation", ticker="NVDA", query="NVDA"
    )
    spec = AnalysisSpec(companies=(nvidia,), metrics=("revenue",))
    result = TurnResult(intent=Intent.LOOKUP, renderer=RendererKind.TABLE, tool_traces=[])

    ideas = suggest_follow_ups(result, spec, ranking)

    assert ideas[0] == "show year-over-year"
    assert ideas[1].startswith("add ") and ideas[1] != "add NVIDIA"
    assert ideas[2] == "add net margin"
    ranked = AnalysisSpec(
        constituents=RankedSet(industry="banks", limit=10, members=()), metrics=()
    )
    assert suggest_follow_ups(result, ranked, ranking) == ["show their revenue", "only the top 5"]


def test_short_names_drop_legal_suffixes() -> None:
    assert short_name("NVIDIA Corporation") == "NVIDIA"
    assert short_name("Eli Lilly and Company") == "Eli Lilly"
    assert short_name("JPMorgan Chase & Co.") == "JPMorgan Chase"
    assert short_name("The Goldman Sachs Group, Inc.") == "Goldman Sachs"


def test_several_metrics_for_one_quarter_read_across_one_row() -> None:
    rows = [
        TableRow(
            company_name="Apple Inc.",
            ticker="AAPL",
            cik="0000320193",
            metric=metric,
            value=Decimal(value),
            start_date=date(2026, 3, 29),
            end_date=date(2026, 6, 27),
        )
        for metric, value in (("revenue", "109420000000"), ("net_margin", "0.272"))
    ]
    result = TurnResult(
        intent=Intent.LOOKUP, renderer=RendererKind.TABLE, table_rows=rows, tool_traces=[]
    )

    table = present_turn(result).table

    assert table is not None
    assert table.keys == ("company_name", "ticker", "value:revenue", "value:net_margin", "end_date")
    assert table.rows == (("Apple Inc.", "AAPL", "$109.42 B", "27.2%", "Jun 27, 2026"),)


def test_a_window_of_several_metrics_reads_one_row_per_quarter_and_change() -> None:
    def row(metric: str, end: date, value: str, comparison: str | None = None) -> TableRow:
        return TableRow(
            company_name="Apple Inc.",
            ticker="AAPL",
            cik="0000320193",
            metric=metric,
            value=Decimal(value),
            end_date=end,
            comparison=comparison,  # type: ignore[arg-type]
        )

    new, old = date(2026, 6, 27), date(2025, 6, 28)
    rows = [
        row("revenue", new, "110"),
        row("net_margin", new, "0.27"),
        row("revenue", old, "100"),
        row("net_margin", old, "0.25"),
        row("revenue", new, "10", "yoy"),
        row("net_margin", new, "0.02", "yoy"),
    ]
    result = TurnResult(
        intent=Intent.LOOKUP, renderer=RendererKind.TABLE, table_rows=rows, tool_traces=[]
    )

    table = present_turn(result).table

    assert table is not None
    assert [r[2] for r in table.rows] == ["Reported", "Reported", "Year over year"]
    assert table.rows[2][3:5] == ("+$10", "+2.0 pts")
