# 07 — Structured LLM planner

**What to build:** Natural-language questions map to the closed intent enum via OpenAI structured outputs so the three live prompts (and explain/news) work without keyword routing. Tests still inject a fake completer. Missing OpenAI config is a typed configuration error, not a regex fallback.

**Blocked by:** 04 — Rank-and-lookup E2E; 05 — Explain with numeral lock E2E; 06 — News-and-explain E2E

**Status:** resolved

- [x] Planner may only emit `lookup` | `compare` | `rank` | `rank_and_lookup` | `explain` | `news_and_explain` (plus parameters)
- [x] The three live prompts and the explain/news backups resolve to the correct intent with the real completer
- [x] Default test suite injects a fake completer and does not call OpenAI
- [x] Missing API key/model raises a configuration error; no canned planner
- [x] Streamlit uses this planner for free-text queries; intent chip still reflects the emitted enum

## Comments

- Fixture/kill-switch still uses `DemoCompleter`. Live `build_runtime()` uses `OpenAIStructuredCompleter`.
- Live planner: `uv run pytest tests/integration/test_live_openai_planner.py -m network`.
- Live SEC/Tavily tests inject `DemoCompleter` so they isolate those APIs from OpenAI.

## Answer

Live turns plan through OpenAI structured outputs constrained to the closed intent enum. Missing `OPENAI_API_KEY`/`OPENAI_MODEL` raises `ConfigurationError` with no regex fallback. Default tests keep injecting a fake completer. Streamlit still shows the emitted intent chip via `run_turn`.
