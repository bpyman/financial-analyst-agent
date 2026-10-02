# 01 — Quarterly lookup E2E

**What to build:** An analyst can ask for a company’s latest quarterly net income (the Google example) and get a table with XBRL provenance in one Streamlit window: intent chip, tool card, accession/concept/period/URL. Offline gold test passes through `run_turn` with a fixture runtime. Live SEC works when credentials are present. `get_financials` is on the local MCP server; identity resolution (including Google → Alphabet) lives inside the tool. The planner is an injectable fake completer so this slice is demoable without OpenAI.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] `run_turn` returns `lookup` + table renderer + provenance for a Google/Alphabet latest-quarter net income query against the fixture runtime
- [x] Streamlit shows intent, tool card, and fact table for that query
- [x] Fact selection is the ported v1 quarterly XBRL rules (standalone duration, no YTD subtraction); unknown metric refuses with the allowed list
- [x] `get_financials` is exposed on local MCP HTTP and used by the turn (in-process or that HTTP), not a stdio-only path
- [x] Default tests are offline; live SEC is optional behind the same fact adapter

## Comments

- Gold tests and inherited fact-selector tests are offline (`pytest` default excludes `network`).
- `FactsPort.get_financials` is shared: `FixtureFactLookup` offline, `SecFactLookup` live. Streamlit and MCP call `build_runtime()` (`APP_MODE=live|fixture`).
- Live Google lookup: `uv run pytest tests/integration/test_live_sec_lookup.py -m network`.

## Answer

`run_turn` on the Google latest-quarter net income query returns `lookup` + a fact table with XBRL provenance. Identity resolution (Google → Alphabet) is inside `get_financials`. Streamlit and local MCP HTTP share the same `FactsPort`. Default tests are offline; live SEC is optional.
