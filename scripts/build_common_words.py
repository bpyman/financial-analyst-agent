"""Build data/common_words.txt: words common across 10-Q filings.

The rules planner corrects a misspelt company name ("Microsft") by closeness
to a listed name, which also turns ordinary words into companies ("being" ->
Boeing, "inflation" -> Infleqtion). A word that most filings use is ordinary
English, not a misspelling, so the planner leaves it alone.

Usage: uv run python scripts/build_common_words.py [html files...]
Default input: the SEC cache's filing documents (.cache/sec/html-*).
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from financial_analyst_agent.filing_change import html_to_text

OUT = Path(__file__).resolve().parent.parent / "src/financial_analyst_agent/data/common_words.txt"
# Only words the planner would try to correct (see issuer_index._TYPO_MIN_LENGTH).
MIN_LENGTH = 5
# Share of filings a word must appear in to count as common. A company name
# in the list does no harm: the planner matches exact names before correcting.
MIN_SHARE = 0.05


def main(paths: list[Path]) -> None:
    documents = Counter[str]()
    for path in paths:
        words = set(re.findall(r"[a-z]+", html_to_text(path.read_text(errors="ignore")).casefold()))
        documents.update(word for word in words if len(word) >= MIN_LENGTH)
    floor = max(2, int(len(paths) * MIN_SHARE))
    common = sorted(word for word, count in documents.items() if count >= floor)
    OUT.write_text("\n".join(common) + "\n", encoding="utf-8")
    print(f"{len(common)} words from {len(paths)} filings -> {OUT}")


if __name__ == "__main__":
    given = [Path(arg) for arg in sys.argv[1:]]
    main(given or sorted(Path(".cache/sec").glob("html-*")))
