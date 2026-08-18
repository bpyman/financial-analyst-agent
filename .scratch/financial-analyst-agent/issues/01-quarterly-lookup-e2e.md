# 01 — Quarterly lookup E2E

**What to build:** An analyst can ask for a company’s latest quarterly net income (the Google example) and get a table with XBRL provenance in one Streamlit window: intent chip, tool card, accession/concept/period/URL. Offline gold test passes through `run_turn` with a fixture runtime. Live SEC works when credentials are present. `get_financials` is on the local MCP server; identity resolution (including Google → Alphabet) lives inside the tool. The planner is an injectable fake completer so this slice is demoable without OpenAI.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `run_turn` returns `lookup` + table renderer + provenance for a Google/Alphabet latest-quarter net income query against the fixture runtime
- [ ] Streamlit shows intent, tool card, and fact table for that query
- [ ] Fact selection is the ported v1 quarterly XBRL rules (standalone duration, no YTD subtraction); unknown metric refuses with the allowed list
- [ ] `get_financials` is exposed on local MCP HTTP and used by the turn (in-process or that HTTP), not a stdio-only path
- [ ] Default tests are offline; live SEC is optional behind the same fact adapter
