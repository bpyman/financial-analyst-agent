# 11 — Say when a quarter's declared dividend covers the year

**What to build:** Walmart declares the year's dividend in its first quarter and tags no dividend paid per share, so its first-quarter cell shows $0.99, four quarters' worth, beside other companies' single-quarter dividends. Within a window, a declared dividend followed by quarters with none ("No dividend declared this quarter") shows the pattern; say then that the declared figure may cover the year, and keep a cross-company comparison from reading it as one quarter's.

Found by the 2026-10-03 review of PRs #45–#58 (PR #48, low).

Spec: ADR 0008.

**Blocked by:** None — can start immediately

**Status:** done

## Answer

presentation.declared_for_year_banners reads the table: within one company's dividends per share, a quarter with a declared figure followed by quarters reading "No dividend declared this quarter" gets a note that the figure may cover the whole year, as when a company declares a year's dividend at once ("may", because a suspension files the same). With other companies in the table, the note adds that the figure may be up to four quarters' worth, not one. A lone declared quarter shows no pattern and gets no note. ADR 0008's dividends row says so; tests in tests/unit/providers/test_dividends_per_share.py run Walmart's recorded filings.
