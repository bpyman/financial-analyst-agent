"""Guide replies and suggested next questions.

Some messages are not analysis requests: a greeting, "what can you do?", "is
Apple a good buy?", or "why?". They get a short, friendly answer that points at
what the window can do, instead of a refusal. Every answer also offers a few
next questions, phrased in words the planner reads, so the analyst can keep
exploring with one tap.
"""

from __future__ import annotations

import re
from typing import Any

from financial_analyst_agent.contracts import (
    FORMULA_METRICS,
    Intent,
    RendererKind,
    TurnResult,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec

STARTER_QUESTIONS: tuple[str, ...] = (
    "How is Nvidia doing?",
    "Compare Apple and Microsoft revenue year over year",
    "Top 5 semiconductor companies by revenue",
    "What changed in Microsoft's latest 10-Q?",
)
HELP_MESSAGE = (
    "I answer from companies' SEC filings. Ask for a quarterly figure (revenue, "
    "net income, margins, EPS, free cash flow), name a period (“Q3 2024”, "
    "“fiscal 2025”), compare companies, rank an industry, track a metric over "
    "several quarters, or see what changed in a 10-Q. Every number links to the "
    "filing it came from."
)
GREETING_MESSAGE = "Hi! " + HELP_MESSAGE
THANKS_MESSAGE = "Glad that helped. Here are a few places to go next."
ADVICE_MESSAGE = (
    "I don't give investment advice or price predictions. I can show what "
    "{subject} filings report, so you can judge for yourself."
)
NOT_RECORDED_MESSAGE = (
    "{name} isn't in the recorded demo. It replays SEC filings for a fixed set of "
    "companies, such as Apple, Microsoft, NVIDIA and JPMorgan Chase. With live "
    "data, any US-listed operating company works."
)
WHY_MESSAGE = (
    "Filings report what happened, not why. Management explains the quarter in "
    "the MD&A section of the 10-Q, and I can show what changed there."
)

_GREETING = re.compile(
    r"^(?:hi|hello|hey|hiya|yo|howdy|good (?:morning|afternoon|evening))(?: there)?$"
)
_HELP = re.compile(
    r"^(?:help|\?|menu|examples?|show me examples|capabilities|what is this|who are you"
    r"|what are you)$"
    r"|\bwhat (?:can|do) you (?:do|answer|know)\b|\bwhat can i ask\b"
    r"|\bhow (?:does this|do i use this|do i use you)\b"
)
_THANKS = re.compile(r"^(?:thanks|thank you|thx|ty|cheers|great|awesome|nice|cool|perfect)\b")
_ADVICE = re.compile(
    r"\b(?:should i (?:buy|sell|invest|hold|short)|(?:good|bad) (?:buy|investment|stock)"
    r"|worth (?:buying|investing)|invest in|price target|stock (?:go up|go down|rise|fall)"
    r"|buy or sell|undervalued|overvalued|buy the dip)\b"
)
_WHY = re.compile(r"^why\b")
_CHART = re.compile(
    r"^(?:can you |please )?(?:chart|plot|graph|visuali[sz]e|draw)(?: it| that| this| them)?$"
)
CHART_MESSAGE = (
    "Charts appear on their own when an answer has several quarters or several "
    "companies. Ask for a window or add a company, and the chart follows."
)
_WHY_MAX_WORDS = 6
_THANKS_MAX_WORDS = 4


def _normalized(message: str) -> str:
    text = message.strip().casefold().replace("’", "'")
    return " ".join(re.sub(r"[!.,]+", " ", text).split()).rstrip(" ?") or text.strip()


def _guide(message: str, suggestions: list[str]) -> TurnResult:
    return TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=message,
        suggestions=suggestions,
        guide=True,
    )


def _spec_company(spec: AnalysisSpec | None) -> tuple[str, str] | None:
    """(display name, planner query) of the current analysis's first company."""
    if spec is None:
        return None
    if spec.companies:
        company = spec.companies[0]
        return short_name(company.name) or company.query, company.query
    return None


def guide_reply(message: str, spec: AnalysisSpec | None, index: Any = None) -> TurnResult | None:
    """A guide answer when the message is not an analysis request, else None."""
    text = _normalized(message)
    if not text:
        return None
    if _GREETING.match(text):
        return _guide(GREETING_MESSAGE, list(STARTER_QUESTIONS))
    if _HELP.search(text) or text == "?":
        return _guide(HELP_MESSAGE, list(STARTER_QUESTIONS))
    if _THANKS.match(text) and len(text.split()) <= _THANKS_MAX_WORDS:
        return _guide(THANKS_MESSAGE, list(STARTER_QUESTIONS[:3]))
    if _ADVICE.search(text):
        named = _named_company(message, index) or _spec_company(spec)
        if named is None:
            return _guide(ADVICE_MESSAGE.format(subject="companies'"), list(STARTER_QUESTIONS))
        name, _query = named
        return _guide(
            ADVICE_MESSAGE.format(subject=f"{name}'s"),
            [
                f"How is {name} doing?",
                f"Show {name}'s revenue year over year",
                f"What changed in {name}'s latest 10-Q?",
            ],
        )
    if _CHART.match(text):
        return _guide(CHART_MESSAGE, ["last 4 quarters", "show year-over-year"])
    if _WHY.match(text) and len(text.split()) <= _WHY_MAX_WORDS:
        named = _spec_company(spec)
        if named is None:
            return _guide(WHY_MESSAGE, list(STARTER_QUESTIONS[3:]))
        name, _query = named
        return _guide(WHY_MESSAGE, [f"What changed in {name}'s latest 10-Q?"])
    return None


def not_recorded_reply(message: str, index: Any, outside: Any) -> TurnResult | None:
    """A reply for a figures question about a company the recording left out.

    ``outside`` is the live snapshot's index on the recorded runtime. A company it
    finds that ``index`` does not was not recorded, and saying so beats answering
    about the companies already on screen.
    """
    missing = _unrecorded_company(message, index, outside)
    if missing is None:
        return None
    return _guide(NOT_RECORDED_MESSAGE.format(name=missing), list(STARTER_QUESTIONS[:3]))


def _unrecorded_company(message: str, index: Any, outside: Any) -> str | None:
    """Display name of a company ``outside`` finds in the message but ``index`` lacks."""
    find = getattr(index, "find", None)
    outside_find = getattr(outside, "find", None)
    if not callable(find) or not callable(outside_find):
        return None
    for mention in outside_find(message):
        if find(mention.typed):
            continue
        display = getattr(outside, "display_name", lambda value: value)(mention.query)
        return short_name(display) or mention.typed
    return None


def _named_company(message: str, index: Any) -> tuple[str, str] | None:
    find = getattr(index, "find", None)
    if not callable(find):
        return None
    mentions = find(message)
    if not mentions:
        return None
    query = mentions[0].query
    display = getattr(index, "display_name", lambda value: value)(query)
    return short_name(display) or query, query


_SUFFIX = re.compile(
    r"(?:,?\s+(?:inc|incorporated|corp|corporation|co|company|ltd|plc|holdings|group"
    r"|& co|and company)\.?)+$",
    re.IGNORECASE,
)


def short_name(name: str) -> str:
    """ "NVIDIA Corporation" → "NVIDIA"; "Eli Lilly and Company" → "Eli Lilly"."""
    short = _SUFFIX.sub("", name.strip()).strip(" ,.")
    # "The Goldman Sachs Group, Inc." reads as "Goldman Sachs".
    return re.sub(r"^the\s+(?=\S)", "", short, flags=re.IGNORECASE)


_METRIC_IDEAS: tuple[str, ...] = ("net_margin", "operating_margin", "revenue", "gross_margin")
_LABELS = {
    "net_margin": "net margin",
    "operating_margin": "operating margin",
    "gross_margin": "gross margin",
    "revenue": "revenue",
    "net_income": "net income",
}
_MAX_SUGGESTIONS = 3
_MAX_COMPANIES_FOR_PEERS = 4


def suggest_follow_ups(result: TurnResult, spec: AnalysisSpec | None, ranking: Any) -> list[str]:
    """Next questions for a finished answer, in words the planner reads."""
    if result.suggestions or result.renderer is RendererKind.CLARIFY:
        return list(result.suggestions)
    if result.renderer is RendererKind.REFUSE:
        return list(STARTER_QUESTIONS[:3]) if spec is None else []
    if spec is None or result.intent not in (
        Intent.LOOKUP,
        Intent.COMPARE,
        Intent.RANK,
        Intent.RANK_AND_LOOKUP,
    ):
        return []
    ideas: list[str] = []
    metrics = set(spec.metrics)
    if spec.constituents is not None:
        for metric in ("revenue", "net_margin", "operating_margin"):
            if metric not in metrics:
                ideas.append(f"show their {_LABELS[metric]}")
                break
        if spec.constituents.limit > 5:
            ideas.append("only the top 5")
        return ideas[:_MAX_SUGGESTIONS]
    if not spec.companies:
        return []
    if "across_periods" not in spec.operations:
        ideas.append("show year-over-year")
    if len(spec.companies) < _MAX_COMPANIES_FOR_PEERS:
        peer = _peer_name(spec, ranking)
        if peer:
            ideas.append(f"add {peer}")
    for metric in _METRIC_IDEAS:
        if metric not in metrics and (metric not in FORMULA_METRICS or len(metrics) < 5):
            ideas.append(f"add {_LABELS[metric]}")
            break
    return ideas[:_MAX_SUGGESTIONS]


_FOREIGN_FORM = re.compile(
    r"\b(?:limited|plc|ag|n\.?v\.?|s\.?a\.?|se|s\.?p\.?a\.?|a/s|asa|ab)\.?$", re.IGNORECASE
)


def _peer_name(spec: AnalysisSpec, ranking: Any) -> str | None:
    peers = getattr(ranking, "peers", None)
    if not callable(peers):
        return None
    ciks = frozenset(company.cik for company in spec.companies if company.cik)
    for company in spec.companies:
        if not company.cik:
            continue
        for peer in peers(company.cik, exclude=ciks, limit=5):
            if _FOREIGN_FORM.search(peer.name):
                # Foreign filers report on 20-F, not 10-Q: a peer with no data.
                continue
            return short_name(peer.name) or peer.ticker
    return None
