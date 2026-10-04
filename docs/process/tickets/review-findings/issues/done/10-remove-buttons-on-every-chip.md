# 10 — Every analysis chip can be removed

**What to build:** PR #50 says "each chip has an ×". The period, operation and ranking chips, and the last company or metric left, have none (`presentation.spec_chip_edits`). Give the period chip an × that returns to the latest quarter, the year-over-year chip one that removes it, and the ranking chip one that clears the ranking; the last company or metric keeps none, since an analysis without one asks nothing, and says so on hover.


The × sends the follow-up a person would type, so that wording has to work first. Today, after "Apple revenue growth last 4 quarters", "remove year over year" and "no year over year" keep the year-over-year column and widen the window to 8 quarters, and "quarter over quarter instead" keeps it and widens the window to 5. Removing year over year drops the comparison and leaves the window, company and metric as they were.

Found by the 2026-10-03 review of PRs #45–#58 (PR #50, partial).

Spec: ADR 0006 (chips send the follow-up a person would type).

**Blocked by:** None — can start immediately

**Status:** done

## Answer

The period chip's × sends "latest quarter" (a window or named period returns to the latest quarter; a chip already at the latest quarter, a snapshot "As of" date and a ranking's period have nothing to undo). The year-over-year chip's × sends "remove year over year", which the shared wording (`request_wording.drops_comparison`) now reads as taking the change away and leaving the window, companies and metric as they were; before, "year over year" in it asked for two years of quarters. The last company, the last metric and a ranking keep no ×, and `ChipEdit.keep` says why on hover. A ranking is the analysis's only subject, so it follows the last company's rule rather than getting an × that clears it: "remove the ranking" today turns the ranking into its member companies, which is not a removal. Switching the base ("quarter over quarter instead") is a separate request and still keeps year over year.
