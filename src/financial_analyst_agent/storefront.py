"""Audience-window copy: guided stories, capabilities, banners.

No UI framework imports here. The HTTP seam serves this text to the window as is.
"""

from __future__ import annotations

from typing import Any

EXAMPLE_QUERY = "What was Google's net income based on their latest quarterly report?"
GUIDED_STORIES: tuple[tuple[str, str], ...] = (
    (
        "Verify a quarterly fact",
        "What was Microsoft's latest quarterly pretax income?",
    ),
    (
        "Compare four quarters",
        "What was Microsoft's quarterly revenue over the last four quarters?",
    ),
    (
        "Rank then inspect filings",
        "What are the top 10 tech companies and R&D spend for each?",
    ),
    (
        "What changed in the 10-Q",
        # The year-apart pair is the recorded one; accession numbers are no question to read.
        "What changed in Microsoft's latest 10-Q?",
    ),
)
CAPABILITIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Look up any quarter's financials, EPS, cash flow, or market cap for any "
        "operating publicly-listed US company",
        (
            "What was Microsoft's latest quarterly revenue?",
            "Apple diluted EPS in Q3 FY2025",
            "Microsoft free cash flow over the last four quarters",
            "How is Nvidia doing?",
        ),
    ),
    (
        "Compare companies on metrics, rank by market cap, or combine rank and lookup",
        (
            "Compare Eli Lilly and Merck net margins",
            "What are the top 10 tech companies and R&D spend for each?",
            "Top 5 semiconductor companies by revenue",
        ),
    ),
    (
        "Access and analyze relevant financial news linked to specific companies",
        ("What's going on with Eli Lilly's obesity drugs?",),
    ),
    (
        "Answer general queries and provide qualitative industry analysis",
        ("How could AI change bank underwriting?",),
    ),
    (
        "Stay on the same thread to extend the current analysis, or start a new one",
        (
            "add Apple",
            "now add operating margin",
            "make that the last four quarters",
            "show year-over-year",
        ),
    ),
)
# The status bar under the header: the runtime's name, then one plain line.
RECORDED_BANNER = (
    "Recorded runtime — captured SEC filings, not a live EDGAR pull. "
    "Numbers go through the same code as live."
)
LIVE_RUNTIME_CAPTION = "Live runtime — figures pulled from SEC EDGAR as you ask."


_NEWS_EXAMPLE = "What's going on with Eli Lilly's obesity drugs?"
_ESSAY_EXAMPLE = "How could AI change bank underwriting?"


def capabilities_for(
    *,
    live_news: bool,
    live_essays: bool,
    recorded_news: str,
    recorded_essay: str,
    live: bool = False,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The capability list with examples this runtime can answer.

    On the recorded runtime, the news and qualitative examples are the
    questions its replay holds, so every example answers. On the live runtime
    without news search or a model those would replay saved stand-ins, so the
    capability is left out rather than advertised.
    """
    swaps = {}
    dropped = set()
    if not live_news:
        swaps[_NEWS_EXAMPLE] = recorded_news
        if live:
            dropped.add(_NEWS_EXAMPLE)
    if not live_essays:
        swaps[_ESSAY_EXAMPLE] = recorded_essay
        if live:
            dropped.add(_ESSAY_EXAMPLE)
    return tuple(
        (description, tuple(swaps.get(example, example) for example in examples))
        for description, examples in CAPABILITIES
        if not dropped.intersection(examples)
    )
LIVE_RUNTIME_LOCKED_NOTICE = "Live runtime is off on the public demo"
# The server lacks SEC_USER_AGENT; the visitor needs only to know live is off.
LIVE_RUNTIME_UNCONFIGURED_NOTICE = "Live runtime is off on this server"
RUNTIME_GUIDE_FOOTER = (
    "A conversation stays on the runtime it started on; switching starts a new one."
)


def runtime_guide(*, live_news: bool, live_essays: bool) -> list[dict[str, Any]]:
    """What each runtime answers from, for the window's "How runtimes differ" panel.

    The flags are whether the live runtime has news search and a writing model
    here, so the panel never promises what this deployment cannot do.
    """
    if live_news and live_essays:
        extras = "Searches recent news and writes analysis with a language model."
    elif live_news:
        extras = "Searches recent news; written analysis is off here."
    elif live_essays:
        extras = "Writes analysis with a language model; news search is off here."
    else:
        extras = "News search and written analysis are off here."
    return [
        {
            "kind": "recorded",
            "name": "Recorded",
            "points": [
                "SEC filings captured ahead of time for a fixed set of large companies: "
                "Apple, JPMorgan, Eli Lilly and about two dozen more.",
                "Answers come back at once and are the same every time; the figures go "
                "through the same code as live.",
                "News and written analysis replay a few saved examples.",
            ],
        },
        {
            "kind": "live",
            "name": "Live",
            "points": [
                "Fetches filings from SEC EDGAR as you ask, for any US-listed company that "
                "files there.",
                "A company's first question takes a few seconds while its filings download.",
                extras,
            ],
        },
    ]

