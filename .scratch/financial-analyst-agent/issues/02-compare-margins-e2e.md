# 02 — Compare and margins E2E

**What to build:** An analyst can ask to compare Microsoft and Google operating margins and see a period-aligned table (or a partial/refuse when periods do not match). Reported facts expand to the locked catalog; margins are Decimal formulas, never LLM arithmetic. Alphabet is one CIK.

**Blocked by:** 01 — Quarterly lookup E2E

**Status:** claimed

- [x] `run_turn` on the MSFT vs GOOG operating-margin prompt returns `compare` and a table of formula results with component provenance
- [x] Period mismatch does not compute a blended margin; partial rows show a typed reason
- [x] GOOG and GOOGL do not produce two issuer rows
- [x] Unknown ratio/metric refuses with the closed reported + formula list
- [x] Streamlit shows the compare table and tool card through the same `run_turn` UI as lookup

## Comments

- Gold tests go through `run_turn` with the fixture runtime or an injected `Runtime` (`pytest` default excludes `network`).
- `operating_margin` is Decimal `operating_income / revenue` from matched-period reported facts; mismatched periods and missing issuer facts become partial rows (`period_mismatch`, `missing_fact`).
- GOOG and GOOGL collapse to one Alphabet CIK inside `compare_metrics`. `compare_metrics` is also on local MCP HTTP; Streamlit still renders via `run_turn`.
