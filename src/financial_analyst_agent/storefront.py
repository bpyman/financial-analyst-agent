"""Audience-window copy: guided stories, capabilities, banners.

No UI framework imports here. The HTTP seam serves this text to the window as is.
"""

from __future__ import annotations

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
LIVE_RUNTIME_LOCKED_NOTICE = "Live runtime is off on the public demo"

