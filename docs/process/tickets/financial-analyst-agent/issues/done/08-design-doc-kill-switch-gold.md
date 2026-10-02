# 08 — Design doc, kill-switch, gold suite

**What to build:** The interview package: a 2–4 page design doc with one diagram and the locked ADRs; a labeled fixture kill-switch that uses the same renderer as live; gold tests for the three live prompts plus one refuse. Demo is rehearsal-ready.

**Blocked by:** 07 — Structured LLM planner

**Status:** resolved

- [x] Design doc + one diagram (user → intent → MCP tools → table vs essay renderer) + ADR list from `prd.md`
- [x] Streamlit kill-switch toggles fixture vs live runtime and is obvious on screen
- [x] Offline gold: Google net income; healthcare top 10 + incomes; MSFT vs GOOG operating margins; one unknown industry or metric refuse
- [x] Kill-switch path uses the same `run_turn` renderer as live (not a separate UI)
- [x] README or design doc states how to run the demo and that kill-switch must be announced if used

## Answer

Interview package is `docs/design.md` (one mermaid diagram + the six PRD ADRs) and a Streamlit sidebar kill-switch that swaps `runtime_for_kill_switch` while still calling `run_turn` and `render_turn_result`. Gold rehearsal is `uv run pytest -m gold` on the three live prompts plus the AI-industry refuse, through fixture runtime.

README states how to run the demo and that the kill-switch must be announced if used.
