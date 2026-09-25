"""Audience-window copy: guided stories, capabilities, banners.

No UI framework imports here. The HTTP seam serves this text to the window as is.
"""

from __future__ import annotations

from financial_analyst_agent.runtime import RECORDED_FILING_NEWER, RECORDED_FILING_OLDER

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
        "What changed in Microsoft's MD&A and Risk Factors between "
        f"{RECORDED_FILING_OLDER} and {RECORDED_FILING_NEWER}?",
    ),
)
CAPABILITIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Look up quarterly 10-Q financial facts or market cap for any "
        "operating publicly-listed US company",
        (
            "What was Microsoft's latest quarterly revenue?",
            "What is Apple's market cap?",
        ),
    ),
    (
        "Compare companies on metrics, rank by market cap, or combine rank and lookup",
        (
            "Compare Eli Lilly and Merck net margins",
            "What are the top 10 tech companies and R&D spend for each?",
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
RECORDED_BANNER = (
    "Recorded runtime — captured SEC filings, not a live EDGAR pull. "
    "Numbers are still produced by the same deterministic renderer."
)
LIVE_RUNTIME_CAPTION = "Live runtime — SEC XBRL, optional planner, cached EDGAR."
LIVE_RUNTIME_LOCKED_NOTICE = "Live runtime is off on the public demo"

