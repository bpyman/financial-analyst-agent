# 07 — Structured LLM planner

**What to build:** Natural-language questions map to the closed intent enum via OpenAI structured outputs so the three live prompts (and explain/news) work without keyword routing. Tests still inject a fake completer. Missing OpenAI config is a typed configuration error, not a regex fallback.

**Blocked by:** 04 — Rank-and-lookup E2E; 05 — Explain with numeral lock E2E; 06 — News-and-explain E2E

**Status:** ready-for-agent

- [ ] Planner may only emit `lookup` | `compare` | `rank` | `rank_and_lookup` | `explain` | `news_and_explain` (plus parameters)
- [ ] The three live prompts and the explain/news backups resolve to the correct intent with the real completer
- [ ] Default test suite injects a fake completer and does not call OpenAI
- [ ] Missing API key/model raises a configuration error; no canned planner
- [ ] Streamlit uses this planner for free-text queries; intent chip still reflects the emitted enum
