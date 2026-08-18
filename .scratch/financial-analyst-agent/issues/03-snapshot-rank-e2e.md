# 03 — Snapshot rank E2E

**What to build:** An analyst can ask for the top 10 healthcare companies and get a sort of the dated US operating-company snapshot (aliases for finance/healthcare/technology, ETFs/funds excluded, timestamp visible). Unknown industry strings including “AI” refuse with the allowed names. A build script can regenerate the snapshot from the market vendor without changing demo ranking membership at request time.

**Blocked by:** 01 — Quarterly lookup E2E

**Status:** ready-for-agent

- [ ] `run_turn` on “top 10 healthcare” returns `rank` and a table from the checked-in snapshot, not a live screener
- [ ] Snapshot timestamp is visible in the UI; fewer than 10 names after filters returns what exists without padding
- [ ] Closed alias table accepts the brief’s industry examples; unknown labels refuse with the allowed list
- [ ] Share classes are consolidated by CIK; ETFs/funds are not ranked
- [ ] Build script produces a snapshot the rank adapter can read; ranking tests inject a fixture snapshot, not live FMP
