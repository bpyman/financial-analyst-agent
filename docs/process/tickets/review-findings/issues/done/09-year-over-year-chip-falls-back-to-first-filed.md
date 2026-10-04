# 09 — The year-over-year chip falls back to the quarter as first filed

**What to build:** ADR 0009 makes the comparative the base of a year-over-year change, and "the year-earlier row as first filed is the base only when the filing reports no comparative". The fact card's chip (`presentation._change_chips`) has no such fallback: with no comparative, the chip is left out. Fetch the year-earlier quarter as first filed when the filing reports no comparative, and draw the chip from it, saying which it is.

This is a fetch more per lookup without a comparative, so check the turn's SEC budget.

Found by the 2026-10-03 review of PRs #45–#58 (PR #50, partial).

Spec: ADR 0009.

**Blocked by:** None — can start immediately

**Status:** done

## Answer

When the fact's own filing reports no year-earlier comparative, `spec_turn.earlier_quarters` (formerly `prior_quarter`) fetches the quarter a year earlier as first filed beside the quarter before, and `TurnResult.year_earlier_rows` carries it to the card. The YoY chip's title then says "as first filed in 10-Q …: the latest filing reports no year-earlier figure"; a comparative, when there is one, still comes first. On the recorded demo this gives balance-sheet figures their chip: Apple cash now shows ▲9.0% YoY against $36.27 B at Jun 28, 2025, beside ▼13.2% QoQ. The budget concern did not hold: both quarters come from the company facts file and filing list the fact was read from, which the SEC cache keeps for an hour, so no further download is needed while they are cached. A base at or below zero still gets no chip (AMD operating income, Bank of America operating cash flow). ADR 0009 now says a 10-Q's balance sheet is compared with the fiscal year-end, and that the card follows the same order.
