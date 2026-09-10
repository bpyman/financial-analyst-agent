"""Deterministic MD&A / Risk Factors diff between two accessions."""

from types import SimpleNamespace

from financial_analyst_agent.contracts import Intent, RendererKind, Runtime
from financial_analyst_agent.filing_change import (
    diff_paragraphs,
    extract_section,
    html_to_text,
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
            return OLDER_HTML
        if accession == NEWER:
            return NEWER_HTML
        raise AssertionError(accession)


class _Facts:
    def __init__(self) -> None:
        self._client = _Client()

    def get_financials(self, company: str, metric: str, **kwargs: object) -> object:
        raise AssertionError("filing change must not look up XBRL facts")

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        return self._client.get_filing_document(cik, accession, document)


def test_extracts_reviewed_sections() -> None:
    mda = extract_section(NEWER_HTML, "mda")
    risk = extract_section(NEWER_HTML, "risk_factors")
    assert "Cloud demand increased" in mda
    assert "Item 3" not in mda
    assert "AI product liability" in risk
    assert "Cloud demand" not in risk


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
    assert all(item.newer_url.endswith("new.htm") for item in changes)


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
        Runtime(completer=SimpleNamespace(), facts=_Facts()),  # type: ignore[arg-type]
    )
    assert result.intent is Intent.FILING_CHANGE
    assert result.renderer is RendererKind.TABLE
    sections = {item.section for item in result.disclosure_changes}
    assert sections == {"mda", "risk_factors"}
    assert result.essay is None
    assert result.tool_traces[0].tool == "filing_change"


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
        Runtime(
            completer=SimpleNamespace(),
            facts=_Facts(),  # type: ignore[arg-type]
            essay=_Essay(),
        ),
    )
    assert result.essay is None
    assert result.numeral_lock_extras
