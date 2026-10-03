# 11 — Say when a quarter's declared dividend covers the year

**What to build:** Walmart declares the year's dividend in its first quarter and tags no dividend paid per share, so its first-quarter cell shows $0.99, four quarters' worth, beside other companies' single-quarter dividends. Within a window, a declared dividend followed by quarters with none ("No dividend declared this quarter") shows the pattern; say then that the declared figure may cover the year, and keep a cross-company comparison from reading it as one quarter's.

Found by the 2026-10-03 review of PRs #45–#58 (PR #48, low).

Spec: ADR 0008.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
