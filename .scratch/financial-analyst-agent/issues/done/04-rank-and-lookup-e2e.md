# 04 — Rank-and-lookup E2E

**What to build:** An analyst can ask for the top 10 healthcare companies and the reported income for each and get one table. Ranking CIKs flow through turn state into fact lookup; the model never retypes the constituent list. Missing facts stay as partial rows.

**Blocked by:** 01 — Quarterly lookup E2E; 03 — Snapshot rank E2E

**Status:** resolved

- [x] `run_turn` on the composed healthcare prompt returns `rank_and_lookup` (not a model-built ticker list)
- [x] Enrichment uses CIKs from the ranking table in graph/turn state
- [x] Partial rows remain when a constituent has no standalone quarterly fact
- [x] Streamlit shows both rank provenance and per-row filing provenance
- [x] Offline gold test covers this prompt against fixture ranking + fixture facts

## Comments

- Gold tests go through `run_turn` with injected fixture ranking + recorded facts (`pytest` default excludes `network`).
- Executor runs `rank_companies`, then `get_financials` with each ranking CIK. Completer ticker lists are ignored. Missing facts stay as `missing_fact` partial rows.
- Streamlit still renders via `run_turn`: snapshot banner + `rank_companies` card, per-CIK `get_financials` cards, and table columns for rank plus filing provenance. No new MCP tool; composition is inside the turn.

## Answer

`run_turn` on the composed healthcare prompt returns `rank_and_lookup` + one table. Constituent enrichment uses ranking CIKs, not a model-typed ticker list. Recorded Lilly/UnitedHealth facts fill; other snapshot names stay partial when no standalone quarter exists.
