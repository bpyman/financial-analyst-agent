# 10 — Period-addressable quarterly facts

**Spec:** 01 — Stateful analysis graph

**What to build:** Ask for a specific quarter, not only the most recent one. Fact lookup can currently answer "the latest quarterly revenue" and nothing else, which is the floor under any trend or year-over-year question. Extend the fact capability so a named quarter is addressable, and the answer is the directly reported standalone-quarter amount for that period with provenance pointing at the filing it actually came from.

The selection rules do not loosen. Still a standalone-quarter duration from a quarterly filing, still no year-to-date subtraction, still no derived Q4, still a typed failure when candidate concepts collide, and still a typed failure when the requested quarter is not reported rather than the nearest available period silently standing in for it. Latest-quarter behaviour is unchanged for every existing caller.

**Blocked by:** 02

**Status:** resolved

- [x] A named quarter can be requested and returns that quarter's directly reported amount with correct filing provenance
- [x] Latest-quarter lookups behave exactly as they do today
- [x] Standalone-duration rules hold, with no year-to-date subtraction and no derived Q4
- [x] A requested quarter that is not reported is a typed failure, never a substituted neighbouring period
- [x] Colliding candidate concepts still fail as an ambiguous concept
- [x] Period selection has unit cases at the fact-selection seam

## Answer

Named quarters are addressable by `report_date` on the fact seam. `get_candidate_filings` and `select_quarterly_fact_with_filing_fallback` take an optional `report_date`; omitted keeps newest-period behaviour. `FactsPort.get_financials` / `SecFactLookup.get_financials` accept the same keyword. A missing named period raises a typed filing failure (surfaced as `UnsupportedQuarterlyFactError` at the port) and never substitutes a neighbour. Standalone-duration, no YTD, no derived Q4, and `AmbiguousFactError` are unchanged. Analysis-spec period windows stay for ticket 11.
