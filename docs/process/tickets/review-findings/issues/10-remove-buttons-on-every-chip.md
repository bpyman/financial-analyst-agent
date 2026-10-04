# 10 — Every analysis chip can be removed

**What to build:** PR #50 says "each chip has an ×". The period, operation and ranking chips, and the last company or metric left, have none (`presentation.spec_chip_edits`). Give the period chip an × that returns to the latest quarter, the year-over-year chip one that removes it, and the ranking chip one that clears the ranking; the last company or metric keeps none, since an analysis without one asks nothing, and says so on hover.

Found by the 2026-10-03 review of PRs #45–#58 (PR #50, partial).

Spec: ADR 0006 (chips send the follow-up a person would type).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
