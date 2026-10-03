# 03 — Snapshot rank E2E

**What to build:** An analyst can ask for the top 10 healthcare companies and get a sort of the dated US operating-company snapshot (aliases for finance/healthcare/technology, ETFs/funds excluded, timestamp visible). Unknown industry strings including “AI” refuse with the allowed names. A build script can regenerate the snapshot from the market vendor without changing demo ranking membership at request time.

**Blocked by:** 01 — Quarterly lookup E2E

**Status:** resolved

- [x] `run_turn` on “top 10 healthcare” returns `rank` and a table from the checked-in snapshot, not a live screener
- [x] Snapshot timestamp is visible in the UI; fewer than 10 names after filters returns what exists without padding
- [x] Closed alias table accepts the brief’s industry examples; unknown labels refuse with the allowed names
- [x] Share classes are consolidated by CIK; ETFs/funds are not ranked
- [x] Build script produces a snapshot the rank adapter can read; ranking tests inject a fixture snapshot, not live FMP

## Comments

- Gold tests go through `run_turn` with the fixture runtime (`pytest` default excludes `network`). Ranking never calls FMP at request time.
- Closed aliases: `finance`/`healthcare`/`technology` (plus canonical FMP sector names present in the snapshot). `banks`/`software` omitted because this freeze does not distinguish them from parent sectors. `AI` refuses with the allowed list.
- Builder (`uv run python scripts/build_universe_snapshot.py` or `--input` stub) drops ETFs/funds/OTC and keeps one row per CIK. `rank_companies` is on local MCP HTTP; Streamlit shows the snapshot timestamp as a banner.
- Follow-up: `run_turn("top 10 healthcare")` matches as `rank` (bare top-N alias, still refuses unknown industries). FMP screener no longer sends `country=US`; rebuild the packaged snapshot to include US-listed foreign issuers such as NVO, AZN, and TSM.
- Follow-up: membership is structural, not an issuer-name catalog. Common-share suffixes and instrument titles drop notes/preferreds/warrants; FMP industries `Shell Companies` and `Financial - Conglomerates` drop SPACs. Asset-management BDCs remain (no isBdc on the screener) and sit outside top-10 finance.

## Answer

`run_turn` on “top 10 healthcare” returns `rank` + a snapshot table with provenance and a visible as-of banner. Unknown industries refuse. Rebuild membership with the snapshot script, not during a demo turn.
