# 09 — The year-over-year chip falls back to the quarter as first filed

**What to build:** ADR 0009 makes the comparative the base of a year-over-year change, and "the year-earlier row as first filed is the base only when the filing reports no comparative". The fact card's chip (`presentation._change_chips`) has no such fallback: with no comparative, the chip is left out. Fetch the year-earlier quarter as first filed when the filing reports no comparative, and draw the chip from it, saying which it is.

This is a fetch more per lookup without a comparative, so check the turn's SEC budget.

Found by the 2026-10-03 review of PRs #45–#58 (PR #50, partial).

Spec: ADR 0009.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
