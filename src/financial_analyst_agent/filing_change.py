"""Accession-pinned filing-section comparison. The model does not pick filings or rewrite diffs."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Any, Literal

from financial_analyst_agent.contracts import (
    MODEL_ANALYSIS_BANNER,
    DisclosureChange,
    Intent,
    RendererKind,
    Runtime,
    ToolTrace,
    TurnResult,
)
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.providers.sec.urls import build_filing_document_url

SectionId = Literal["mda", "risk_factors"]

REVIEWED_SECTIONS: tuple[SectionId, ...] = ("mda", "risk_factors")
SECTION_LABELS: dict[SectionId, str] = {
    "mda": "Management's Discussion and Analysis",
    "risk_factors": "Risk Factors",
}
_SECTION_HEADINGS: dict[SectionId, re.Pattern[str]] = {
    "mda": re.compile(
        r"item\s+(?:2|7)\s*[.:]?\s*management['’]?s?\s+discussion",
        re.IGNORECASE,
    ),
    "risk_factors": re.compile(r"item\s+1a\s*[.:]?\s*risk\s+factors", re.IGNORECASE),
}
_NEXT_ITEM = re.compile(r"\nitem\s+\d+[a-z]?\s*[.:]", re.IGNORECASE)
_SECTION_ALIASES: dict[str, SectionId] = {
    "md&a": "mda",
    "mda": "mda",
    "management's discussion": "mda",
    "management discussion": "mda",
    "risk factors": "risk_factors",
    "risk factor": "risk_factors",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip = True
        if tag in {"p", "div", "br", "tr", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip = False
        if tag in {"p", "div", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in parser.text().splitlines()]
    return "\n".join(line for line in lines if line)


def extract_section(html: str, section: SectionId) -> str:
    text = html_to_text(html)
    match = _SECTION_HEADINGS[section].search(text)
    if match is None:
        return ""
    rest = text[match.start() :]
    nxt = _NEXT_ITEM.search(rest, pos=len(match.group(0)))
    body = rest if nxt is None else rest[: nxt.start()]
    return body.strip()


def _paragraphs(section_text: str) -> list[str]:
    blocks = [part.strip() for part in re.split(r"\n{2,}", section_text) if part.strip()]
    if len(blocks) <= 1:
        blocks = [line.strip() for line in section_text.splitlines() if line.strip()]
    return [block for block in blocks if len(block) > 20 or block.lower().startswith("item")]


def diff_paragraphs(
    older: str,
    newer: str,
    *,
    section: SectionId,
    older_accession: str,
    newer_accession: str,
    older_url: str,
    newer_url: str,
) -> list[DisclosureChange]:
    left = _paragraphs(older)
    right = _paragraphs(newer)
    matcher = SequenceMatcher(a=left, b=right, autojunk=False)
    changes: list[DisclosureChange] = []
    label = SECTION_LABELS[section]
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            for paragraph in right[j1:j2]:
                changes.append(
                    DisclosureChange(
                        section=section,
                        section_label=label,
                        change_kind="added",
                        after_text=paragraph,
                        older_accession=older_accession,
                        newer_accession=newer_accession,
                        older_url=older_url,
                        newer_url=newer_url,
                    )
                )
        elif tag == "delete":
            for paragraph in left[i1:i2]:
                changes.append(
                    DisclosureChange(
                        section=section,
                        section_label=label,
                        change_kind="removed",
                        before_text=paragraph,
                        older_accession=older_accession,
                        newer_accession=newer_accession,
                        older_url=older_url,
                        newer_url=newer_url,
                    )
                )
        else:
            before = "\n\n".join(left[i1:i2])
            after = "\n\n".join(right[j1:j2])
            changes.append(
                DisclosureChange(
                    section=section,
                    section_label=label,
                    change_kind="changed",
                    before_text=before,
                    after_text=after,
                    older_accession=older_accession,
                    newer_accession=newer_accession,
                    older_url=older_url,
                    newer_url=newer_url,
                )
            )
    return changes


def parse_sections(raw: str) -> tuple[SectionId, ...]:
    lowered = raw.casefold()
    found: list[SectionId] = []
    if "both" in lowered or "and risk" in lowered:
        return REVIEWED_SECTIONS
    for alias, section in _SECTION_ALIASES.items():
        if alias in lowered and section not in found:
            found.append(section)
    if not found:
        return ("mda",)
    return tuple(found)


def _document_for(runtime: Runtime, cik: str, accession: str, document: str) -> str:
    facts = runtime.facts
    getter = getattr(facts, "get_filing_document", None)
    if not callable(getter):
        inner = getattr(facts, "_inner", facts)
        getter = getattr(inner, "get_filing_document", None)
    if not callable(getter):
        client = getattr(getattr(facts, "_inner", facts), "_client", None)
        getter = getattr(client, "get_filing_document", None)
    if not callable(getter):
        raise ProviderError("Filing documents are not available on this runtime")
    return str(getter(cik, accession, document))


def _tickers_payload(runtime: Runtime) -> dict[str, Any]:
    facts = runtime.facts
    inner = getattr(facts, "_inner", facts)
    client = getattr(inner, "_client", None)
    if client is None:
        raise ProviderError("Company identity is not available on this runtime")
    payload = client.get_company_tickers()
    if not isinstance(payload, dict):
        raise ProviderError("Company ticker payload must be an object")
    return payload


def _primary_document(runtime: Runtime, cik: str, accession: str) -> str:
    facts = runtime.facts
    inner = getattr(facts, "_inner", facts)
    client = getattr(inner, "_client", None)
    if client is None or not hasattr(client, "get_submissions"):
        return "primary.htm"
    from financial_analyst_agent.providers.sec.submissions import parse_submissions

    filings = parse_submissions(client.get_submissions(cik))
    for filing in filings:
        if filing.accession_number == accession:
            return filing.primary_document or "primary.htm"
    return "primary.htm"


def run_filing_change(plan: Any, runtime: Runtime) -> TurnResult:
    company = str(getattr(plan, "company", "") or "")
    older = str(getattr(plan, "older_accession", "") or "")
    newer = str(getattr(plan, "newer_accession", "") or "")
    sections = parse_sections(str(getattr(plan, "section", "mda")))
    traces = [
        ToolTrace(
            tool="filing_change",
            args={
                "company": company,
                "older_accession": older,
                "newer_accession": newer,
                "sections": list(sections),
            },
        )
    ]
    if not company or not older or not newer:
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message="Filing change needs one company and two accession numbers.",
        )
    try:
        resolved = resolve_company(company, _tickers_payload(runtime))
    except Exception as exc:
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    cik = resolved.cik
    changes: list[DisclosureChange] = []
    try:
        for section in sections:
            older_doc = _primary_document(runtime, cik, older)
            newer_doc = _primary_document(runtime, cik, newer)
            older_html = _document_for(runtime, cik, older, older_doc)
            newer_html = _document_for(runtime, cik, newer, newer_doc)
            older_url = build_filing_document_url(cik, older, older_doc)
            newer_url = build_filing_document_url(cik, newer, newer_doc)
            older_section = extract_section(older_html, section)
            newer_section = extract_section(newer_html, section)
            if not older_section or not newer_section:
                traces[0] = traces[0].model_copy(
                    update={
                        "provenance": {
                            "error": f"Reviewed section {SECTION_LABELS[section]} was not found"
                        }
                    }
                )
                continue
            changes.extend(
                diff_paragraphs(
                    older_section,
                    newer_section,
                    section=section,
                    older_accession=older,
                    newer_accession=newer,
                    older_url=older_url,
                    newer_url=newer_url,
                )
            )
    except ProviderError as exc:
        traces[0] = traces[0].model_copy(
            update={"provenance": {"error": {"code": exc.code, "message": str(exc)}}}
        )
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=str(exc),
        )
    if not changes:
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message="No reviewed-section changes were found between those filings.",
        )
    traces[0] = traces[0].model_copy(
        update={"provenance": {"change_count": len(changes), "cik": cik}}
    )
    grounding = json.dumps(
        [item.model_dump(mode="json") for item in changes],
        default=str,
    )
    essay = None
    extras: list[str] = []
    banners: list[str] = []
    if runtime.essay is not None and getattr(plan, "summarize", False):
        from financial_analyst_agent.turn import _numeral_lock_extras

        topic = (
            f"Summarize only the following disclosure changes for {resolved.name}. "
            "Do not invent numbers."
        )
        try:
            essay = runtime.essay.complete_essay(topic, grounding)
            extras = _numeral_lock_extras(essay, grounding)
            banners = [MODEL_ANALYSIS_BANNER]
            if extras:
                essay = None
        except ProviderError:
            essay = None
    return TurnResult(
        intent=Intent.FILING_CHANGE,
        tool_traces=traces,
        renderer=RendererKind.TABLE,
        disclosure_changes=changes,
        essay=essay,
        banners=banners,
        numeral_lock_extras=extras,
    )
