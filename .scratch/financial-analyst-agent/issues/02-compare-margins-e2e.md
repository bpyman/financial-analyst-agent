# 02 — Compare and margins E2E

**What to build:** An analyst can ask to compare Microsoft and Google operating margins and see a period-aligned table (or a partial/refuse when periods do not match). Reported facts expand to the locked catalog; margins are Decimal formulas, never LLM arithmetic. Alphabet is one CIK.

**Blocked by:** 01 — Quarterly lookup E2E

**Status:** ready-for-agent

- [ ] `run_turn` on the MSFT vs GOOG operating-margin prompt returns `compare` and a table of formula results with component provenance
- [ ] Period mismatch does not compute a blended margin; partial rows show a typed reason
- [ ] GOOG and GOOGL do not produce two issuer rows
- [ ] Unknown ratio/metric refuses with the closed reported + formula list
- [ ] Streamlit shows the compare table and tool card through the same `run_turn` UI as lookup
