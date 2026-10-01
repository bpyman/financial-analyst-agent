"""Deterministic MD&A / Risk Factors diff between two accessions."""

import json
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent.contracts import MODEL_ANALYSIS_BANNER, Intent, RendererKind, Runtime
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.filing_change import (
    SectionId,
    diff_paragraphs,
    extract_section,
    filing_anchor_url,
    html_to_text,
    parse_sections,
    run_filing_change,
)

OLDER_HTML = """
<html><body>
<div>Item 1A. Risk Factors</div>
<p>We face competition in cloud services.</p>
<p>Regulatory change could affect our licenses.</p>
<div>Item 2. Management's Discussion and Analysis</div>
<p>Cloud demand was stable during the quarter.</p>
<p>Capital spending stayed flat.</p>
<div>Item 3. Quantitative and Qualitative Disclosures About Market Risk</div>
<p>Not meaningful.</p>
</body></html>
"""

NEWER_HTML = """
<html><body>
<div>Item 1A. Risk Factors</div>
<p>We face competition in cloud services.</p>
<p>AI product liability is an emerging risk.</p>
<div>Item 2. Management's Discussion and Analysis</div>
<p>Cloud demand increased during the quarter.</p>
<p>Capital spending rose for AI infrastructure.</p>
<div>Item 3. Quantitative and Qualitative Disclosures About Market Risk</div>
<p>Not meaningful.</p>
</body></html>
"""

OLDER = "0001193125-25-000099"
NEWER = "0001193125-26-191507"
CIK = "0000789019"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("risk_factors", ("risk_factors",)),
        ("RISK_FACTORS", ("risk_factors",)),
        ("mda", ("mda",)),
        ("mda,risk_factors", ("mda", "risk_factors")),
        ("Risk Factors", ("risk_factors",)),
    ],
)
def test_parse_sections_accepts_canonical_ids(raw: str, expected: tuple[str, ...]) -> None:
    assert parse_sections(raw) == expected


class _Client:
    def get_company_tickers(self) -> dict[str, object]:
        return {
            "0": {
                "cik_str": "789019",
                "ticker": "MSFT",
                "title": "Microsoft Corporation",
            }
        }

    def get_submissions(self, cik: str) -> dict[str, object]:
        assert cik == CIK
        return {
            "cik": 789019,
            "name": "Microsoft Corporation",
            "tickers": ["MSFT"],
            "filings": {
                "recent": {
                    "form": ["10-Q", "10-Q"],
                    "accessionNumber": [NEWER, OLDER],
                    "filingDate": ["2026-04-29", "2025-01-30"],
                    "reportDate": ["2026-03-31", "2024-12-31"],
                    "primaryDocument": ["msft-20260331.htm", "msft-20241231.htm"],
                }
            },
        }

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        assert cik == CIK
        if accession == OLDER:
            assert document == "msft-20241231.htm"
            return OLDER_HTML
        if accession == NEWER:
            assert document == "msft-20260331.htm"
            return NEWER_HTML
        raise AssertionError(accession)


class _Facts:
    def __init__(self) -> None:
        # The SEC source filing change reads, passed as the runtime's filings port.
        self._client = _Client()

    def get_financials(self, company: str, metric: str, **kwargs: object) -> object:
        raise AssertionError("filing change must not look up XBRL facts")


def _runtime(facts: _Facts | None = None, **kwargs: Any) -> Runtime:
    facts = facts or _Facts()
    return Runtime(
        completer=SimpleNamespace(),  # type: ignore[arg-type]
        facts=facts,  # type: ignore[arg-type]
        filings=facts._client,
        **kwargs,
    )


def test_extracts_reviewed_sections() -> None:
    mda = extract_section(NEWER_HTML, "mda")
    risk = extract_section(NEWER_HTML, "risk_factors")
    assert "Cloud demand increased" in mda
    assert "Item 3" not in mda
    assert "AI product liability" in risk
    assert "Cloud demand" not in risk


def test_a_cross_reference_is_not_the_section_it_names() -> None:
    # Pfizer's 10-Q: MD&A cites "the Item 1A. Risk Factors section" mid-sentence
    # many times before Part II's own short Item 1A.
    html = """
    <h2>ITEM 2. MANAGEMENT'S DISCUSSION AND ANALYSIS</h2>
    <p>For manufacturing risks, see the Item 1A. Risk Factors section of our 2025 Form 10-K.</p>
    <p>Revenue grew on strong demand for our medicines across every region.</p>
    <h2>ITEM 3. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h2>
    <p>Market risk paragraph.</p>
    <p>PART II. OTHER INFORMATION Item 1A. Risk Factors</p>
    <p>We refer to the Item 1A. Risk Factors section of our 2025 Form 10-K.</p>
    <h2>ITEM 2. UNREGISTERED SALES OF EQUITY SECURITIES</h2>
    """

    risk = extract_section(html, "risk_factors")
    mda = extract_section(html, "mda")

    # A "PART II" label before the heading on its line still makes it a heading.
    assert risk.startswith("Item 1A. Risk Factors\nWe refer to")
    assert "Revenue grew" not in risk
    assert "Market risk" not in risk
    assert "Revenue grew" in mda


_LONG = " ".join(["Net interest income rose on higher deposit balances and loan growth."] * 40)


def test_mda_listed_only_in_the_contents_is_found_by_its_parts() -> None:
    # JPMorgan's 10-Q: "Item 2" appears only in the contents, above MD&A's parts
    # and their pages; the body uses the parts as headings, in capitals.
    html = f"""
    <p>TABLE OF CONTENTS</p>
    <p>Item 1.</p><p>Financial Statements</p>
    <p>Consolidated statements of income (unaudited) for the three months ended June 30</p><p>93</p>
    <p>Notes to Consolidated Financial Statements</p><p>98</p>
    <p>Item 2.</p>
    <p>Management’s Discussion and Analysis of Financial Condition and Results of Operations.</p>
    <p>Introduction</p><p>4</p>
    <p>Executive Overview</p><p>5</p>
    <p>Forward-Looking Statements</p><p>92</p>
    <p>Item 3.</p><p>Quantitative and Qualitative Disclosures About Market Risk.</p><p>201</p>
    <p>INTRODUCTION</p>
    <p>{_LONG}</p>
    <p>EXECUTIVE OVERVIEW</p>
    <p>Firmwide results were strong across every line of business this quarter.</p>
    <p>FORWARD-LOOKING STATEMENTS</p>
    <p>Statements here are forward-looking and subject to risks.</p>
    <p>92</p>
    <p>Consolidated statements of income (unaudited)</p>
    <p>Revenue table that is not MD&amp;A.</p>
    """

    mda = extract_section(html, "mda")

    assert mda.startswith("INTRODUCTION")
    assert "Firmwide results were strong" in mda
    assert "forward-looking and subject to risks" in mda
    assert "Revenue table" not in mda


def test_a_bare_mda_heading_after_its_contents_entry_starts_the_section() -> None:
    # Intel's 10-Q orders content its own way; "Item 2" is only in a closing index.
    html = f"""
    <p>Table of Contents</p>
    <p>Consolidated Condensed Statements of Operations</p><p>3</p>
    <p>Management's Discussion and Analysis (MD&amp;A)</p>
    <p>Operating Segments Trends and Results</p><p>30</p>
    <p>Liquidity and Capital Resources</p><p>39</p>
    <p>Risk Factors and Other Key Information</p>
    <p>Risk Factors</p><p>41</p>
    <p>Management's Discussion and Analysis</p>
    <p>Overview</p>
    <p>{_LONG}</p>
    <p>Liquidity and Capital Resources</p>
    <p>Cash from operations funded capital spending in the quarter.</p>
    <p>Risk Factors and Other Key Information</p>
    <p>Risk Factors</p>
    <p>The risks described in our Form 10-K could hurt our business.</p>
    """

    mda = extract_section(html, "mda")

    assert mda.startswith("Management's Discussion and Analysis\nOverview")
    assert "Cash from operations" in mda
    assert "could hurt our business" not in mda


def test_an_item_heading_may_use_a_dash() -> None:
    html = """
    <p>Item 2 — Management’s discussion and analysis of financial condition</p>
    <p>Sales grew in every segment during the quarter.</p>
    <p>Item 3 — Quantitative and qualitative disclosures about market risk</p>
    <p>Market risk text.</p>
    """

    mda = extract_section(html, "mda")

    assert "Sales grew" in mda
    assert "Market risk text" not in mda


def test_a_filing_that_only_cites_risk_factors_has_no_section() -> None:
    html = """
    <h2>ITEM 2. MANAGEMENT'S DISCUSSION AND ANALYSIS</h2>
    <p>Other factors are discussed under "Item 1A. Risk Factors" of our 2025 Form 10-K.</p>
    <h2>ITEM 3. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h2>
    """

    assert extract_section(html, "risk_factors") == ""


def test_a_disclosure_on_its_heading_line_is_the_section() -> None:
    html = (
        "<p>Item 1A. Risk Factors 42</p>"
        "<p>Item 2. Unregistered Sales of Equity Securities 43</p>"
        "<p>Item 1A. Risk Factors. There have been no material changes to our risk factors.</p>"
        "<p>Item 2. Unregistered Sales of Equity Securities</p>"
    )

    assert extract_section(html, "risk_factors") == (
        "Item 1A. Risk Factors. There have been no material changes to our risk factors."
    )


@pytest.mark.parametrize("punctuation", [".", ":", ""])
@pytest.mark.parametrize(
    ("section", "heading", "next_heading"),
    [
        ("risk_factors", "Item 1A{punctuation} Risk Factors", "Item 1B"),
        ("mda", "Item 2{punctuation} Management's Discussion and Analysis", "Item 3"),
        ("mda", "Item 7{punctuation} Management’s Discussion and Analysis", "Item 7A"),
    ],
)
def test_extract_section_skips_toc_and_retains_repeated_body_headings(
    section: SectionId, heading: str, next_heading: str, punctuation: str
) -> None:
    title = heading.format(punctuation=punctuation)
    html = f"""
    <div>Table of Contents</div>
    <table><tr><td>{title}</td><td>12</td></tr>
    <tr><td>{next_heading}{punctuation} Other disclosures</td><td>20</td></tr></table>
    <h2>{title}</h2>
    <p>First actual disclosure paragraph must remain in the extracted section.</p>
    <h2>{title} (continued)</h2>
    <p>Second actual disclosure paragraph must remain in the extracted section.</p>
    <h2>{next_heading}{punctuation} Other disclosures</h2>
    <p>Unrelated disclosure must not be included.</p>
    """

    extracted = extract_section(html, section)

    assert extracted.startswith(title + "\n")
    assert "First actual disclosure" in extracted
    assert "Second actual disclosure" in extracted
    assert "Other disclosures" not in extracted
    assert "Unrelated disclosure" not in extracted


def test_diff_compares_body_changes_despite_identical_toc() -> None:
    toc = """
    <div>Item 1A. Risk Factors</div>
    <div>Item 2. Management's Discussion and Analysis</div>
    <div>Item 3. Market Risk</div>
    """
    changes = diff_paragraphs(
        extract_section(toc + OLDER_HTML, "risk_factors"),
        extract_section(toc + NEWER_HTML, "risk_factors"),
        section="risk_factors",
        older_accession=OLDER,
        newer_accession=NEWER,
        older_url="https://www.sec.gov/old.htm",
        newer_url="https://www.sec.gov/new.htm",
    )

    assert len(changes) == 1
    assert changes[0].before_text == "Regulatory change could affect our licenses."
    assert changes[0].after_text == "AI product liability is an emerging risk."


def test_html_to_text_drops_tags() -> None:
    assert "<p>" not in html_to_text(NEWER_HTML)
    assert "Cloud demand increased" in html_to_text(NEWER_HTML)


def test_paragraph_diff_is_deterministic() -> None:
    older = extract_section(OLDER_HTML, "mda")
    newer = extract_section(NEWER_HTML, "mda")
    changes = diff_paragraphs(
        older,
        newer,
        section="mda",
        older_accession=OLDER,
        newer_accession=NEWER,
        older_url="https://www.sec.gov/old.htm",
        newer_url="https://www.sec.gov/new.htm",
    )
    kinds = {item.change_kind for item in changes}
    assert "changed" in kinds or "added" in kinds
    assert all(item.older_accession == OLDER for item in changes)
    assert all(
        item.newer_url.startswith("https://www.sec.gov/new.htm#:~:text=")
        for item in changes
    )
    assert all(
        item.older_url.startswith("https://www.sec.gov/old.htm#:~:text=")
        for item in changes
    )


def test_run_filing_change_maps_both_reviewed_sections() -> None:
    result = run_filing_change(
        SimpleNamespace(
            intent=Intent.FILING_CHANGE,
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="MD&A and Risk Factors",
            summarize=False,
        ),
        _runtime(),
    )
    assert result.intent is Intent.FILING_CHANGE
    assert result.renderer is RendererKind.TABLE
    sections = {item.section for item in result.disclosure_changes}
    assert sections == {"mda", "risk_factors"}
    assert result.essay is None
    assert result.tool_traces[0].tool == "filing_change"


@pytest.mark.parametrize("form", ["10-K", "10-K/A", "10-Q", "10-Q/A"])
def test_run_filing_change_resolves_actual_primary_document(
    monkeypatch: pytest.MonkeyPatch, form: str
) -> None:
    facts = _Facts()
    payload: dict[str, Any] = facts._client.get_submissions(CIK)
    payload["filings"]["recent"]["form"] = [form, form]
    monkeypatch.setattr(facts._client, "get_submissions", lambda cik: payload)

    result = run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="risk_factors",
        ),
        _runtime(facts),
    )

    assert result.renderer is RendererKind.TABLE
    assert {change.section for change in result.disclosure_changes} == {"risk_factors"}
    older_base = (
        "https://www.sec.gov/Archives/edgar/data/789019/000119312525000099/msft-20241231.htm"
    )
    newer_base = (
        "https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/msft-20260331.htm"
    )
    assert all(
        change.older_url.startswith(older_base) and "#:~:text=" in change.older_url
        and change.newer_url.startswith(newer_base) and "#:~:text=" in change.newer_url
        for change in result.disclosure_changes
    )


def test_filing_anchor_url_encodes_section_text() -> None:
    url = "https://www.sec.gov/Archives/edgar/data/789019/msft.htm"
    anchored = filing_anchor_url(url, "Item 2. Management's Discussion")
    assert anchored.startswith(url + "#:~:text=")
    assert "Management" in anchored


@pytest.mark.parametrize(
    "problem",
    [
        "unknown_accession",
        "missing_document",
        "empty_document",
        "blank_document",
        "missing_field",
        "no_submissions",
    ],
)
def test_run_filing_change_refuses_unresolved_document(
    monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    facts = _Facts()
    payload: dict[str, Any] = facts._client.get_submissions(CIK)
    recent = payload["filings"]["recent"]
    if problem == "unknown_accession":
        recent["accessionNumber"][1] = "0001193125-25-000098"
    elif problem == "missing_field":
        del recent["primaryDocument"]
    elif problem == "missing_document":
        recent["primaryDocument"][1] = None
    elif problem == "empty_document":
        recent["primaryDocument"][1] = ""
    elif problem == "blank_document":
        recent["primaryDocument"][1] = "   "
    monkeypatch.setattr(facts._client, "get_submissions", lambda cik: payload)
    if problem == "no_submissions":

        def unavailable(cik: str) -> dict[str, object]:
            raise ProviderError("SEC submissions are unavailable")

        monkeypatch.setattr(facts._client, "get_submissions", unavailable)

    def unexpected_download(*args: object) -> str:
        pytest.fail("Unresolved documents must be refused before downloading")

    monkeypatch.setattr(facts._client, "get_filing_document", unexpected_download)
    result = run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="mda",
        ),
        _runtime(facts),
    )

    assert result.renderer is RendererKind.REFUSE
    assert not result.disclosure_changes
    assert result.tool_traces[0].provenance["error"]


def test_numeral_lock_drops_invented_summary_numbers() -> None:
    class _Essay:
        def complete_essay(self, query: str, tool_json: str = "") -> str:
            return "Revenue jumped to 999 billion based on the filings."

    result = run_filing_change(
        SimpleNamespace(
            intent=Intent.FILING_CHANGE,
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="mda",
            summarize=True,
        ),
        _runtime(essay=_Essay()),
    )
    assert result.essay is None
    # The table still answers, so extras stay off the result and go on the trace.
    assert result.numeral_lock_extras == []
    assert result.tool_traces[0].provenance["summary_numeral_lock"]
    # The model-analysis banner labels a summary; none is shown, so say why instead.
    assert MODEL_ANALYSIS_BANNER not in result.banners
    assert any("withheld" in banner for banner in result.banners)


def test_run_filing_change_refuses_without_a_company_or_with_one_accession() -> None:
    for company, older in (("", ""), ("Microsoft", "0000950170-25-061046")):
        result = run_filing_change(
            SimpleNamespace(
                intent=Intent.FILING_CHANGE,
                company=company,
                older_accession=older,
                newer_accession="",
                section="mda",
            ),
            _runtime(),
        )
        assert result.renderer is RendererKind.REFUSE
        assert "accession" in (result.message or "").lower()
        assert not result.disclosure_changes


def test_run_filing_change_without_accessions_picks_a_year_apart() -> None:
    result = run_filing_change(
        SimpleNamespace(
            intent=Intent.FILING_CHANGE,
            company="Microsoft",
            older_accession="",
            newer_accession="",
            section="mda",
        ),
        _runtime(),
    )
    assert result.renderer is RendererKind.TABLE
    assert result.disclosure_changes
    assert any("latest 10-Q" in banner for banner in result.banners)


def test_filing_change_banner_uses_the_snapshot_name() -> None:
    class _NamedFacts(_Facts):
        def display_name(self, cik: str, fallback: str) -> str:
            return "The Microsoft Company, Inc." if cik == CIK else fallback

    result = run_filing_change(
        SimpleNamespace(
            intent=Intent.FILING_CHANGE,
            company="Microsoft",
            older_accession="",
            newer_accession="",
            section="mda",
        ),
        _runtime(_NamedFacts()),
    )

    assert any(banner.startswith("Comparing Microsoft's latest 10-Q") for banner in result.banners)


def test_run_filing_change_orders_accessions_by_report_date() -> None:
    result = run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession=NEWER,
            newer_accession=OLDER,
            section="mda",
        ),
        _runtime(),
    )
    assert result.renderer is RendererKind.TABLE
    assert {item.older_accession for item in result.disclosure_changes} == {OLDER}
    assert {item.newer_accession for item in result.disclosure_changes} == {NEWER}


def test_run_filing_change_uses_query_accessions_not_plan() -> None:
    result = run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession="0000000000-00-000000",
            newer_accession="1111111111-11-111111",
            section="mda",
        ),
        _runtime(),
        query=f"What changed in Microsoft's MD&A between {OLDER} and {NEWER}?",
    )
    assert result.renderer is RendererKind.TABLE
    assert {item.older_accession for item in result.disclosure_changes} == {OLDER}


def test_run_filing_change_ignores_planner_accessions_absent_from_query() -> None:
    # The model never picks filings: accessions only it proposed are dropped and
    # deterministic code picks a year-apart pair instead, saying so.
    result = run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="mda",
        ),
        _runtime(),
        query="What changed in Microsoft's MD&A",
    )
    assert any("latest 10-Q" in banner for banner in result.banners)


def test_partial_section_failure_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    import financial_analyst_agent.filing_change as filing_change

    original = filing_change._section_from_text

    def missing_risk(text: str, section: str) -> str:
        if section == "risk_factors":
            return ""
        return original(text, section)

    monkeypatch.setattr(filing_change, "_section_from_text", missing_risk)
    result = filing_change.run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="mda and risk_factors",
        ),
        _runtime(),
    )
    assert result.renderer is RendererKind.TABLE
    assert {item.section for item in result.disclosure_changes} == {"mda"}
    assert result.tool_traces[0].provenance["section_errors"] == ["Risk Factors was not found"]
    assert (
        "I couldn't find the Risk Factors section in one or both of these filings, so only "
        "Management's Discussion and Analysis was compared."
    ) in result.banners


def _unchanged_facts(monkeypatch: pytest.MonkeyPatch) -> _Facts:
    """Both filings carry the same text, so every section that can be read is unchanged."""
    facts = _Facts()
    monkeypatch.setattr(
        facts._client, "get_filing_document", lambda cik, accession, document: OLDER_HTML
    )
    return facts


def _without(monkeypatch: pytest.MonkeyPatch, *missing: str) -> None:
    import financial_analyst_agent.filing_change as filing_change

    original = filing_change._section_from_text

    def extract(text: str, section: str) -> str:
        return "" if section in missing else original(text, section)

    monkeypatch.setattr(filing_change, "_section_from_text", extract)


def _both_sections(facts: _Facts) -> Any:
    return run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="mda and risk_factors",
        ),
        _runtime(facts),
    )


def test_unchanged_filings_say_no_changes_were_found(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _both_sections(_unchanged_facts(monkeypatch))
    assert result.renderer is RendererKind.REFUSE
    assert result.message == "No reviewed-section changes were found between those filings."
    assert "section_errors" not in result.tool_traces[0].provenance


def test_unreadable_sections_are_not_reported_as_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without(monkeypatch, "mda", "risk_factors")
    result = _both_sections(_Facts())
    assert result.renderer is RendererKind.REFUSE
    assert result.message == (
        "I couldn't find the Management's Discussion and Analysis or Risk Factors "
        "sections in one or both of these filings, so I couldn't compare them."
    )
    assert result.tool_traces[0].provenance["section_errors"] == [
        "Management's Discussion and Analysis was not found",
        "Risk Factors was not found",
    ]


def test_one_unreadable_section_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    _without(monkeypatch, "risk_factors")
    result = run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="risk_factors",
        ),
        _runtime(),
    )
    assert result.renderer is RendererKind.REFUSE
    assert result.message == (
        "I couldn't find the Risk Factors section in one or both of these filings, "
        "so I couldn't compare it."
    )


def test_no_changes_is_claimed_only_for_the_sections_compared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without(monkeypatch, "risk_factors")
    result = _both_sections(_unchanged_facts(monkeypatch))
    assert result.renderer is RendererKind.REFUSE
    assert result.message == (
        "Management's Discussion and Analysis did not change between these filings. "
        "I couldn't find the Risk Factors section in one or both of these filings, "
        "so it was not compared."
    )
    assert result.tool_traces[0].provenance["section_errors"] == ["Risk Factors was not found"]


def test_a_summary_the_model_cannot_write_is_explained() -> None:
    from financial_analyst_agent.domain.errors import ProviderError

    class _Essay:
        def complete_essay(self, query: str, tool_json: str = "") -> str:
            raise ProviderError("No summary is shown for these filings.")

    result = run_filing_change(
        SimpleNamespace(
            company="Microsoft",
            older_accession=OLDER,
            newer_accession=NEWER,
            section="mda",
            summarize=True,
        ),
        _runtime(essay=_Essay()),
    )
    assert result.renderer is RendererKind.TABLE
    assert result.disclosure_changes
    assert result.essay is None
    assert MODEL_ANALYSIS_BANNER not in result.banners
    assert "No summary is shown for these filings." in result.banners


def test_run_filing_change_refuses_a_fund(monkeypatch: pytest.MonkeyPatch) -> None:
    import financial_analyst_agent.universe as universe

    monkeypatch.setattr(universe, "INELIGIBLE_ISSUER_CIKS", frozenset({"0000789019"}))

    result = run_filing_change(
        SimpleNamespace(
            intent=Intent.FILING_CHANGE,
            company="MSFT",
            older_accession="",
            newer_accession="",
            section="mda",
        ),
        _runtime(),
    )

    assert result.renderer is RendererKind.REFUSE
    assert "not an operating company" in (result.message or "")


def test_numeral_lock_does_not_ground_figures_on_links_or_accessions() -> None:
    from financial_analyst_agent.turn import _numeral_lock_extras

    grounding = json.dumps(
        [
            {
                "older_accession": "0000950170-25-061046",
                "newer_url": "https://www.sec.gov/Archives/edgar/data/789019/000095017026000123/x.htm",
                "after": "Revenue grew 12% in the quarter.",
            }
        ]
    )

    assert _numeral_lock_extras("Revenue grew 12%.", grounding) == []
    assert _numeral_lock_extras("Revenue grew 25%.", grounding) == ["25"]
    assert _numeral_lock_extras("Margins hit 789019.", grounding) == ["789019"]


def test_numeral_lock_treats_dates_as_dates_not_figures() -> None:
    from financial_analyst_agent.turn import _numeral_lock_extras

    grounding = json.dumps([{"value": "245122000000", "end_date": "2026-03-31"}])

    # A date's parts do not unlock a figure...
    assert _numeral_lock_extras("Revenue rose 31%.", grounding) == ["31"]
    assert _numeral_lock_extras("Margins moved 03 points.", grounding) == ["03"]
    # ...and a date written in the essay is not scanned as one.
    assert _numeral_lock_extras(
        "Revenue was 245122000000 in the quarter ended March 31, 2026.", grounding
    ) == []
    assert _numeral_lock_extras("In fiscal 2026 revenue rose.", grounding) == []
    # A list comma and the next word are not part of a number.
    assert _numeral_lock_extras("It grew 29, then 30.", grounding) == ["29", "30"]
    # A year is a date only beside a word that dates it; an amount stays an amount.
    assert _numeral_lock_extras("Revenue was 2050 million dollars.", grounding) == [
        "2050 million"
    ]
    assert _numeral_lock_extras("USD 1999 million on buybacks", grounding) == ["1999 million"]
    assert _numeral_lock_extras("They plan to hire 2000 engineers.", grounding) == ["2000"]
    assert _numeral_lock_extras("Sales rose in March 12% year over year.", grounding) == ["12"]
    # The source's years may be quoted: its dates are 2026.
    assert _numeral_lock_extras("2026 was a strong year.", grounding) == []
    assert _numeral_lock_extras("In 2025, revenue rose.", grounding) == []


def test_table_cells_are_separated_in_filing_text() -> None:
    html = "<table><tr><td>Noninterest revenue</td><td>$24,470</td></tr></table>"

    assert html_to_text(html) == "Noninterest revenue $24,470"


def _diff(older: str, newer: str) -> list[Any]:
    return diff_paragraphs(
        older,
        newer,
        section="mda",
        older_accession="a",
        newer_accession="b",
        older_url="",
        newer_url="",
    )


def test_footers_figure_rows_and_short_dates_are_not_changes() -> None:
    prose = "Demand for cloud services grew across every region we serve this quarter."
    footer = "Apple Inc. | Q3 2026 Form 10-Q | {page}"
    older = "\n\n".join(
        [
            prose,
            footer.format(page=12),
            "Revenue in the quarter ended Jul 26, 2025 rose as shown on pages 22-26.",
            footer.format(page=13),
            "Noninterest revenue $24,470 $22,037 11 %",
            footer.format(page=14),
        ]
    )
    newer = "\n\n".join(
        [
            prose,
            footer.format(page=15),
            "Revenue in the quarter ended Jul 25, 2026 rose as shown on pages 27-34.",
            footer.format(page=16),
            "Noninterest revenue $25,100 $24,470 3 %",
            footer.format(page=17),
        ]
    )

    assert _diff(older, newer) == []


def test_templated_sentences_that_repeat_are_still_compared() -> None:
    older = "\n\n".join(f"Revenue increased ${n}.1 billion or {n}0%." for n in (1, 2, 3))
    newer = "\n\n".join(f"Revenue increased ${n}.2 billion or {n}1%." for n in (1, 2, 3))

    assert len(_diff(older, newer)) == 1


@pytest.mark.parametrize(
    ("query", "company", "others", "expected"),
    [
        ("Changes in 0000950170-25-061046 vs 0000950170-25-061046?", "MSFT", (), "same filing"),
        (
            "Compare 0000950170-25-061046 0001193125-26-191507 0001193125-26-323660",
            "MSFT",
            (),
            "exactly two",
        ),
        ("What changed in Microsoft and Apple's 10-Q?", "Microsoft", ("Apple",), "one company"),
        ("What changed in the latest 10-Q?", "unknown", (), "which company"),
    ],
)
def test_filing_change_requests_it_cannot_compare_say_why(
    query: str, company: str, others: tuple[str, ...], expected: str
) -> None:
    from financial_analyst_agent.filing_change import _request_refusal

    plan = SimpleNamespace(other_companies=others)

    assert expected in _request_refusal(query, company, "", "", plan)


def test_a_10k_question_compares_10ks_and_20f_filers_are_named() -> None:
    from financial_analyst_agent.filing_change import _form_asked, _too_few_message

    assert _form_asked("What changed in Microsoft's latest 10-K?") == "10-K"
    assert _form_asked("What changed in Microsoft's latest 10-Q?") == "10-Q"
    assert "20-F" in _too_few_message({"form": ["20-F", "6-K"]}, "Taiwan Semiconductor", "10-Q")


def test_an_annual_report_or_accession_question_is_a_filing_change() -> None:
    from financial_analyst_agent.rules_planner import DemoCompleter

    for question in (
        "What changed in Microsoft's latest 10-K?",
        "What changed between 0000950170-25-061046 and 0001193125-26-191507?",
    ):
        assert DemoCompleter().complete(question).intent is Intent.FILING_CHANGE


def test_a_change_names_the_heading_it_sits_under() -> None:
    older = "\n".join(
        [
            "LIQUIDITY AND CAPITAL RESOURCES",
            "We expect existing cash to be sufficient for the next twelve months of needs.",
            "Percentage",
            "Revenue 10 % 12 %",
        ]
    )
    newer = older.replace("for the next twelve", "for at least the next twelve")

    (change,) = _diff(older, newer)

    assert change.subsection == "Liquidity and Capital Resources"
