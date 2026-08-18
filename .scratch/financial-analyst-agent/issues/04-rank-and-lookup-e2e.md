# 04 — Rank-and-lookup E2E

**What to build:** An analyst can ask for the top 10 healthcare companies and the reported income for each and get one table. Ranking CIKs flow through turn state into fact lookup; the model never retypes the constituent list. Missing facts stay as partial rows.

**Blocked by:** 01 — Quarterly lookup E2E; 03 — Snapshot rank E2E

**Status:** ready-for-agent

- [ ] `run_turn` on the composed healthcare prompt returns `rank_and_lookup` (not a model-built ticker list)
- [ ] Enrichment uses CIKs from the ranking table in graph/turn state
- [ ] Partial rows remain when a constituent has no standalone quarterly fact
- [ ] Streamlit shows both rank provenance and per-row filing provenance
- [ ] Offline gold test covers this prompt against fixture ranking + fixture facts
