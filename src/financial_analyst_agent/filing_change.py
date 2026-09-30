"""Accession-pinned filing-section comparison. The model does not pick filings or rewrite diffs."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import quote

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
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.observability import call_provider
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.providers.sec.urls import build_filing_document_url
from financial_analyst_agent.universe import INELIGIBLE_ISSUER_CIKS

SectionId = Literal["mda", "risk_factors"]

REVIEWED_SECTIONS: tuple[SectionId, ...] = ("mda", "risk_factors")
SECTION_LABELS: dict[SectionId, str] = {
    "mda": "Management's Discussion and Analysis",
    "risk_factors": "Risk Factors",
}
_SECTION_HEADINGS: dict[SectionId, re.Pattern[str]] = {
    "mda": re.compile(
        r"item\s+(?:2|7)\s*[.:—–-]?\s*management['’]?s?\s+discussion",
        re.IGNORECASE,
    ),
    "risk_factors": re.compile(r"item\s+1a\s*[.:—–-]?\s*risk\s+factors", re.IGNORECASE),
}
_NEXT_ITEM = re.compile(r"^item\s+\d+[a-z]?(?=[\s.:—–-]|$)", re.IGNORECASE | re.MULTILINE)
# A bare "Item 2" line, no punctuation or title, repeated down the pages is a
# running header (Microsoft prints one on every page), not the next section.
_BARE_ITEM = re.compile(r"^item\s+\d+[a-z]?$", re.IGNORECASE | re.MULTILINE)
_RUNNING_HEADER_REPEATS = 3
# Disclosure on the heading's own line ("Item 1A. Risk Factors. There have been
# no material changes..."): a full stop, then a sentence ending in one.
_SENTENCE = re.compile(r"\.\s+[A-Za-z].*\w\.\s*$")
# A contents entry taken for a section: nothing under its heading but a page.
_STUB_BODY = re.compile(r"^\W*(?:pages?\s*)?\d{0,3}(?:\s*[-–]\s*\d{1,3})?\W*$", re.IGNORECASE)
# What may precede a heading on its line: "PART II — OTHER INFORMATION Item 1A. …".
_PART_LABEL = re.compile(r"part\s+i{1,2}\b.{0,60}", re.IGNORECASE)
_ACCESSION_PATTERN = re.compile(r"\d{10}-\d{2}-\d{6}")
_SECTION_ALIASES: dict[str, SectionId] = {
    "md&a": "mda",
    "mda": "mda",
    "management's discussion": "mda",
    "management discussion": "mda",
    "risk factors": "risk_factors",
    "risk factor": "risk_factors",
    "risk_factors": "risk_factors",
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
        elif tag in {"td", "th"}:
            # "Noninterest revenue" and "$24,470" are two cells, not one word.
            self._chunks.append(" ")

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


def filing_anchor_url(url: str, snippet: str) -> str:
    """Point a filing URL at the reviewed section or changed paragraph."""
    text = " ".join(snippet.split())
    if not url or not text:
        return url
    if "#:~:text=" in url:
        return url
    return f"{url}#:~:text={quote(text[:96], safe='')}"


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in parser.text().splitlines()]
    return "\n".join(line for line in lines if line)


def _starts_line(text: str, start: int) -> bool:
    """Whether a heading match opens its line, as a heading does.

    A cross-reference ("see the Item 1A. Risk Factors section of our 2025 Form
    10-K") sits mid-sentence; taken as a heading, it ran to the next Item and
    filed pages of MD&A under Risk Factors.
    """
    before = text[text.rfind("\n", 0, start) + 1 : start].strip()
    return not before or _PART_LABEL.fullmatch(before) is not None


# An MD&A shorter than this under its Item heading is a contents entry, not the section.
_SHORT_MDA = 2000


def extract_section(html: str, section: SectionId) -> str:
    text = html_to_text(html)
    found = _section_under_item(text, section)
    if section == "mda" and len(found) < _SHORT_MDA:
        # Banks and some others (JPMorgan, Wells Fargo, Intel) file MD&A under
        # their own headings and list it only in the table of contents.
        from_contents = _mda_from_contents(text)
        if len(from_contents) > len(found):
            return from_contents
    return found


def _section_under_item(text: str, section: SectionId) -> str:
    heading = _SECTION_HEADINGS[section]
    bare = Counter(line.casefold() for line in _BARE_ITEM.findall(text))
    running = {line for line, count in bare.items() if count >= _RUNNING_HEADER_REPEATS}
    candidates: list[str] = []
    for match in heading.finditer(text):
        if not _starts_line(text, match.start()):
            continue
        end = len(text)
        for next_item in _NEXT_ITEM.finditer(text, match.end()):
            line_end = text.find("\n", next_item.start())
            line = text[next_item.start() : len(text) if line_end < 0 else line_end]
            if line.strip().casefold() in running:
                continue
            if heading.match(text, next_item.start()) is None:
                end = next_item.start()
                break
        found = text[match.start() : end].strip()
        body = found.split("\n", 1)[1] if "\n" in found else ""
        same_line = found.split("\n", 1)[0][match.end() - match.start() :]
        if _STUB_BODY.fullmatch(body.strip()) and not _SENTENCE.search(same_line):
            continue
        candidates.append(found)
    return max(candidates, key=len, default="")


_MDA_TITLE = re.compile(
    r"^(?:item\s*[27]\s*[.:—–-]?\s*)?management['’]?s\s+discussion\s+and\s+analysis\b",
    re.IGNORECASE,
)
_SPLIT_ITEM = re.compile(r"item\s*[27]\s*[.:]?", re.IGNORECASE)
_LINE_ITEM = re.compile(r"^item\s*\d+[a-z]?\b", re.IGNORECASE)
_PAGE = re.compile(r"^(?:pages?\s+)?(\d{1,3})(?:\s*[-–]\s*\d{1,3})?$", re.IGNORECASE)
# Contents entries: a title of at most this many characters, then its page on the next line.
_MAX_TITLE = 120
# A listed MD&A part this many pages past the one before it (a glossary at the
# back of the report) is not where MD&A ends.
_OUTLYING_PAGES = 40
# Unpaired lines ("Part II", "Page") a contents page may have between entries.
_CONTENTS_GAP = 4


def _norm_title(line: str) -> str:
    return " ".join(line.strip(" .:").casefold().replace("’", "'").split())


class _Contents:
    """The table of contents in a filing's text lines: titles followed by page numbers."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def page(self, k: int) -> int | None:
        if not 0 <= k < len(self.lines):
            return None
        match = _PAGE.match(self.lines[k].strip())
        return int(match.group(1)) if match else None

    def is_entry(self, k: int) -> bool:
        title = self.lines[k].strip()
        return (
            self.page(k + 1) is not None
            and 2 < len(title) <= _MAX_TITLE
            and self.page(k) is None
            and not title.startswith(("(", "•"))
        )

    def entries(self, k: int, step: int, stop: int) -> list[int]:
        found: list[int] = []
        gap = 0
        while 0 <= k < stop and gap <= _CONTENTS_GAP:
            if self.is_entry(k):
                gap = 0
                found.append(k)
            else:
                gap += 1
            k += step
        return found


def _mda_from_contents(text: str) -> str:
    """MD&A found through the table of contents, for filings with no Item 2 heading over it.

    The contents list MD&A's parts with their pages ("Executive Overview 5");
    the body uses those parts as headings. MD&A runs from its first heading
    to the heading of the next contents entry by page.
    """
    lines = text.split("\n")
    contents = _Contents(lines)
    for i, line in enumerate(lines):
        split = _SPLIT_ITEM.fullmatch(line.strip()) is not None and i + 1 < len(lines)
        title = f"{line} {lines[i + 1]}" if split else line
        if not _MDA_TITLE.match(title.strip()):
            continue
        j = i + 1 + int(split)
        parts: list[tuple[str, int]] = []
        while j < len(lines) and contents.is_entry(j) and not _LINE_ITEM.match(lines[j].strip()):
            page = contents.page(j + 1)
            assert page is not None
            parts.append((_norm_title(lines[j]), page))
            j += 2
        if len(parts) < 2:
            continue
        part_titles = {part for part, _ in parts}
        start = next(
            (
                k
                for k in range(j, len(lines))
                if not contents.is_entry(k)
                and not _LINE_ITEM.match(lines[k].strip())
                and (_MDA_TITLE.match(lines[k].strip()) or _norm_title(lines[k]) in part_titles)
            ),
            None,
        )
        if start is None:
            return ""
        # Other entries of the same contents page, before MD&A's entry and after
        # it up to where the body starts.
        indexes = contents.entries(i - 1, -1, len(lines)) + contents.entries(j, 1, start)
        pages = sorted(page for _, page in parts)
        while len(pages) > 1 and pages[-1] - pages[-2] > _OUTLYING_PAGES:
            pages.pop()
        after: dict[str, int] = {}
        for k in indexes:
            title_k, page_k = _norm_title(lines[k]), contents.page(k + 1)
            if page_k is not None and page_k > pages[-1] and title_k not in part_titles:
                after.setdefault(title_k, page_k)
        return "\n".join(lines[start : _mda_end(lines, contents, start, after)]).strip()
    return ""


def _mda_end(lines: list[str], contents: _Contents, start: int, after: dict[str, int]) -> int:
    """The line where the next contents entry's heading, or an Item heading, begins."""
    titles = [title for title in after if len(title) >= 8]
    for k in range(start + 3, len(lines)):
        line = _norm_title(lines[k])
        heading = len(line) >= 8 and any(
            (line.startswith(title) and len(line) <= len(title) + 25) or title.startswith(line)
            for title in titles
        )
        if heading or (_LINE_ITEM.match(lines[k].strip()) and not contents.is_entry(k)):
            return k
    # No heading found: stop after the footer of the page before the next entry.
    if after:
        last_page = min(after.values()) - 1
        for k in range(start + 3, len(lines)):
            if contents.page(k) == last_page:
                return k + 1
    return len(lines)


# A filing pair can differ in hundreds of paragraphs (JPMorgan: 367, 524 KB).
MAX_CHANGES_SHOWN = 60
_SUMMARIZED_CHANGES = 30
_SUMMARY_TEXT_CHARS = 1500


def _blocks(section_text: str) -> list[str]:
    blocks = [part.strip() for part in re.split(r"\n{2,}", section_text) if part.strip()]
    if len(blocks) <= 1:
        blocks = [line.strip() for line in section_text.splitlines() if line.strip()]
    return [block for block in blocks if len(block) > 20 or block.lower().startswith("item")]


def _paragraphs(section_text: str) -> list[str]:
    """The section's prose: no running footers, and no rows that are mostly figures."""
    blocks = _blocks(section_text)
    # A running footer repeats word for word but for its page number ("Apple Inc. |
    # Q3 2026 Form 10-Q | 18"); a segment's "Revenue increased $7.9 billion"
    # repeats only its wording, and each is a disclosure.
    repeats = Counter(_PAGE_NUMBER.sub("", block) for block in blocks)
    return [
        block
        for block in blocks
        if repeats[_PAGE_NUMBER.sub("", block)] < _RUNNING_HEADER_REPEATS
        and not _is_figures(block)
    ]


def _is_figures(block: str) -> bool:
    """A table row of amounts ("Noninterest revenue $24,470 $22,037 11 %"), not prose.

    It holds as many numbers as words; "Revenue increased $7.9 billion or 30%." is
    a sentence.
    """
    tokens = block.split()
    numbers = sum(any(char.isdigit() for char in token) for token in tokens)
    words = sum(token.isalpha() for token in tokens)
    return numbers >= 2 and numbers >= words


def _figure_rows(section_text: str) -> set[str]:
    return {
        _undated(block)
        for block in _blocks(section_text)
        if _is_figures(block)
    }


_PAGE_NUMBER = re.compile(r"[\s|•·–-]*\d{1,3}\s*$")
_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?"
)
# Dates, years (also one run into the next word, "2024Drivers") and page
# references move from one filing to the next without the disclosure changing.
_DATES = re.compile(
    rf"\b{_MONTH}\s+\d{{1,2}},?\s+(?:19|20)\d{{2}}(?!\d)"
    r"|(?<!\d)(?:19|20)\d{2}(?!\d)"
    r"|\bpages?\s+\d{1,3}(?:\s*[-–]\s*\d{1,3})?\b",
    re.IGNORECASE,
)


def _undated(paragraph: str) -> str:
    """The paragraph with its dates and years masked, for matching across a year."""
    return _DATES.sub("<date>", " ".join(paragraph.split()))


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
    # Matched with dates masked: a paragraph that differs only by its dates ("the
    # quarter ended March 31, 2026" a year on) is the same disclosure, not a change.
    matcher = SequenceMatcher(
        a=[_undated(text) for text in left], b=[_undated(text) for text in right], autojunk=False
    )
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
                        older_url=filing_anchor_url(older_url, label),
                        newer_url=filing_anchor_url(newer_url, paragraph),
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
                        older_url=filing_anchor_url(older_url, paragraph),
                        newer_url=filing_anchor_url(newer_url, label),
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
                    older_url=filing_anchor_url(older_url, before),
                    newer_url=filing_anchor_url(newer_url, after),
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


def _submissions_recent(runtime: Runtime, cik: str) -> dict[str, Any]:
    facts = runtime.facts
    inner = getattr(facts, "_inner", facts)
    client = getattr(inner, "_client", None)
    getter = getattr(client, "get_submissions", None)
    if not callable(getter):
        raise ProviderError("Filing submissions are not available on this runtime")
    payload = getter(cik)
    if not isinstance(payload, dict) or not isinstance(payload.get("filings"), dict):
        raise ProviderError("submissions payload missing filings object")
    recent = payload["filings"].get("recent")
    if not isinstance(recent, dict):
        raise ProviderError("submissions payload missing filings.recent object")
    return recent


def _primary_document(runtime: Runtime, cik: str, accession: str) -> str:
    recent = _submissions_recent(runtime, cik)
    accessions = recent.get("accessionNumber")
    documents = recent.get("primaryDocument")
    forms = recent.get("form")
    if (
        not isinstance(accessions, list)
        or not isinstance(documents, list)
        or not isinstance(forms, list)
    ):
        raise ProviderError("submissions accessionNumber, primaryDocument and form must be lists")
    if len(accessions) != len(documents) or len(accessions) != len(forms):
        raise ProviderError("submissions filing arrays have inconsistent lengths")
    for index, candidate in enumerate(accessions):
        if candidate == accession and forms[index] in ("10-Q", "10-Q/A", "10-K", "10-K/A"):
            document = documents[index]
            if isinstance(document, str) and document.strip():
                return document
            raise ProviderError(f"Primary document is missing for accession {accession}")
    raise ProviderError(f"Filing accession {accession} was not found in supported submissions")


def _pretty(iso: str) -> str:
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{day:%b} {day.day}, {day.year}"


_YEAR = 365
_SAME_QUARTER_DAYS = 20


def _year_apart_quarterlies(recent: dict[str, Any]) -> tuple[str, str] | None:
    """The newest 10-Q and the 10-Q for the same quarter a year before it.

    A year apart compares like with like: the same fiscal quarter, so seasonal
    wording does not read as change. Without one, the previous 10-Q stands in.
    """
    accessions = recent.get("accessionNumber")
    forms = recent.get("form")
    dates = recent.get("reportDate")
    if not (isinstance(accessions, list) and isinstance(forms, list) and isinstance(dates, list)):
        return None
    quarterlies: list[tuple[date, str]] = []
    for accession, form, raw in zip(accessions, forms, dates, strict=False):
        if form != "10-Q" or not isinstance(raw, str) or not isinstance(accession, str):
            continue
        try:
            quarterlies.append((date.fromisoformat(raw), accession))
        except ValueError:
            continue
    quarterlies.sort(reverse=True)
    if len(quarterlies) < 2:
        return None
    newest_date, newest = quarterlies[0]
    for when, accession in quarterlies[1:]:
        if abs((newest_date - when).days - _YEAR) <= _SAME_QUARTER_DAYS:
            return accession, newest
    return quarterlies[1][1], newest


def _filing_date(recent: dict[str, Any], accession: str) -> str:
    accessions = recent.get("accessionNumber")
    if not isinstance(accessions, list):
        return ""
    dates = recent.get("reportDate")
    if not isinstance(dates, list):
        dates = recent.get("filingDate")
    if not isinstance(dates, list) or len(dates) != len(accessions):
        return ""
    for index, candidate in enumerate(accessions):
        if candidate == accession:
            value = dates[index]
            return value.strip() if isinstance(value, str) else ""
    return ""


def _order_accessions(recent: dict[str, Any], first: str, second: str) -> tuple[str, str]:
    left = _filing_date(recent, first)
    right = _filing_date(recent, second)
    if left and right and left > right:
        return second, first
    return first, second


def _accessions_from_query(query: str, plan_older: str, plan_newer: str) -> tuple[str, str]:
    found = _ACCESSION_PATTERN.findall(query)
    if query.strip():
        if len(found) >= 2:
            return found[0], found[1]
        if found:
            return found[0], ""
        return "", ""
    return plan_older, plan_newer


# Whole words only: "Verisk", "Riskified" and "Waste Management" name companies,
# not sections.
_RISK_WORDS = r"risk\s+factors?|risks?"
_MDA_WORDS = r"md&a|mda|management['’]?s?\s+discussion(?:\s+and\s+analysis)?"
_NEGATION = (
    r"(?:not|no|excluding|exclude|except|without|other\s+than|but\s+not)\s+(?:the\s+|its\s+)?"
)
_RISK = re.compile(rf"\b(?:{_RISK_WORDS})\b", re.IGNORECASE)
_MDA = re.compile(rf"(?<![\w&])(?:{_MDA_WORDS})\b", re.IGNORECASE)
_NOT_RISK = re.compile(rf"\b{_NEGATION}(?:{_RISK_WORDS})\b", re.IGNORECASE)
_NOT_MDA = re.compile(rf"\b{_NEGATION}(?:{_MDA_WORDS})\b", re.IGNORECASE)


def requested_sections(text: str) -> str | None:
    """The reviewed sections a question names: "mda", "risk_factors", both, or None.

    "MD&A, not the risk factors" and "excluding risk factors" leave a section
    out; a question naming neither asks about the whole filing.
    """
    risk = _RISK.search(text) is not None and _NOT_RISK.search(text) is None
    mda = _MDA.search(text) is not None and _NOT_MDA.search(text) is None
    excluded_risk = _NOT_RISK.search(text) is not None
    excluded_mda = _NOT_MDA.search(text) is not None
    if risk and mda:
        return "mda and risk_factors"
    if risk or (excluded_mda and not mda):
        return "risk_factors"
    if mda or excluded_risk:
        return "mda"
    if re.search(r"\bboth\b", text, re.IGNORECASE):
        return "mda and risk_factors"
    return None


def _section_choice(query: str, fallback: str) -> str:
    return requested_sections(query) or fallback


def _labels(sections: list[SectionId]) -> str:
    return " and ".join(SECTION_LABELS[section] for section in sections)


def _unreadable_sentence(unreadable: list[SectionId]) -> str:
    noun = "section" if len(unreadable) == 1 else "sections"
    missing = " or ".join(SECTION_LABELS[section] for section in unreadable)
    return f"I couldn't find the {missing} {noun} in one or both of these filings"


def _unchanged_message(compared: list[SectionId], unreadable: list[SectionId]) -> str:
    if not unreadable:
        return "No reviewed-section changes were found between those filings."
    if not compared:
        pronoun = "it" if len(unreadable) == 1 else "them"
        return f"{_unreadable_sentence(unreadable)}, so I couldn't compare {pronoun}."
    return (
        f"{_labels(compared)} did not change between these filings. "
        f"{_unreadable_sentence(unreadable)}, so it was not compared."
    )


def run_filing_change(plan: Any, runtime: Runtime, *, query: str = "") -> TurnResult:
    company = str(getattr(plan, "company", "") or "")
    older, newer = _accessions_from_query(
        query,
        str(getattr(plan, "older_accession", "") or ""),
        str(getattr(plan, "newer_accession", "") or ""),
    )
    sections = parse_sections(_section_choice(query, str(getattr(plan, "section", "mda"))))
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
    if not company or company == "unknown" or bool(older) != bool(newer):
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=(
                "Name one company to compare its latest 10-Q with the same quarter a "
                "year earlier, or give two accession numbers."
            ),
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
    if cik in INELIGIBLE_ISSUER_CIKS:
        # The same membership rule lookups and rankings apply (ADR 0001).
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=(
                f"{resolved.name} is not an operating company (it is a fund, business "
                "development company or similar listing), so its filings are outside "
                "what this analyst covers."
            ),
        )
    # SEC titles companies "PFIZER INC"; the snapshot knows them as "Pfizer Inc.".
    display = getattr(runtime.facts, "display_name", None)
    name = display(cik, resolved.name) if callable(display) else resolved.name
    chosen_banner = ""
    changes: list[DisclosureChange] = []
    figure_rows = 0
    section_errors: list[str] = []
    compared: list[SectionId] = []
    unreadable: list[SectionId] = []
    try:
        recent = _submissions_recent(runtime, cik)
        if not older:
            pair = _year_apart_quarterlies(recent)
            if pair is None:
                raise ProviderError("Fewer than two 10-Q filings are available for this company")
            older, newer = pair
            chosen_banner = (
                f"Comparing {short_name(name)}'s latest 10-Q (quarter ended "
                f"{_pretty(_filing_date(recent, newer))}) with the one for "
                f"{_pretty(_filing_date(recent, older))}."
            )
        older, newer = _order_accessions(recent, older, newer)
        traces[0] = traces[0].model_copy(
            update={
                "args": {
                    **traces[0].args,
                    "older_accession": older,
                    "newer_accession": newer,
                }
            }
        )
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
                section_errors.append(f"{SECTION_LABELS[section]} was not found")
                unreadable.append(section)
                continue
            compared.append(section)
            figure_rows += len(_figure_rows(newer_section) - _figure_rows(older_section))
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
    traces[0] = traces[0].model_copy(
        update={
            "provenance": {
                "change_count": len(changes),
                "cik": cik,
                **({"section_errors": section_errors} if section_errors else {}),
            }
        }
    )
    if not changes:
        # "No changes" is claimed only for sections both filings let us compare.
        return TurnResult(
            intent=Intent.FILING_CHANGE,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=_unchanged_message(compared, unreadable),
        )
    banners: list[str] = [chosen_banner] if chosen_banner else []
    if unreadable:
        banners.append(
            _unreadable_sentence(unreadable)
            + f", so only {_labels(compared)} was compared."
        )
    if figure_rows:
        rows = "row" if figure_rows == 1 else "rows"
        banners.append(
            f"{figure_rows} table {rows} of figures changed too and are left out here; "
            "ask for a metric to see the figures with their sources."
        )
    if len(changes) > MAX_CHANGES_SHOWN:
        banners.append(
            f"Showing the first {MAX_CHANGES_SHOWN} of {len(changes)} changes, in the "
            "order they appear in the filing."
        )
        changes = changes[:MAX_CHANGES_SHOWN]
    # The model reads the first changes, each cut to a length it can weigh.
    grounding = json.dumps(
        [
            item.model_copy(
                update={
                    "before_text": item.before_text[:_SUMMARY_TEXT_CHARS],
                    "after_text": item.after_text[:_SUMMARY_TEXT_CHARS],
                }
            ).model_dump(mode="json")
            for item in changes[:_SUMMARIZED_CHANGES]
        ],
        default=str,
    )
    essay = None
    extras: list[str] = []
    if runtime.essay is not None and getattr(plan, "summarize", False):
        from financial_analyst_agent.turn import _numeral_lock_extras

        topic = (
            f"Summarize only the following disclosure changes for {name}. "
            "Do not invent numbers."
        )
        essay_completer = runtime.essay
        try:
            essay = call_provider(
                "llm", lambda: essay_completer.complete_essay(topic, grounding)
            )
            extras = _numeral_lock_extras(essay, grounding)
            if extras:
                # The summary is withheld; say why rather than label nothing.
                essay = None
                banners.append(
                    "The model's summary was withheld because it quoted numbers "
                    "that are not in these filings."
                )
            else:
                banners.append(MODEL_ANALYSIS_BANNER)
        except ProviderError as exc:
            # The changes stand on their own; say plainly why no summary is shown.
            essay = None
            banners.append(str(exc))
    return TurnResult(
        intent=Intent.FILING_CHANGE,
        tool_traces=traces,
        renderer=RendererKind.TABLE,
        disclosure_changes=changes,
        essay=essay,
        banners=banners,
        numeral_lock_extras=extras,
    )
