# 05 — Explain with numeral lock E2E

**What to build:** An analyst can ask how AI can disrupt healthcare and get a labeled model-analysis essay with no retrieval and no invented numbers. Structured turns still render as tables; this path is the essay renderer plus numeral lock.

**Blocked by:** 01 — Quarterly lookup E2E

**Status:** ready-for-agent

- [ ] `run_turn` on an industry/AI explain prompt returns `explain`, essay renderer, and a model-analysis banner
- [ ] Essay contains no numeric tokens that were not in tool JSON (explain has no numeric tools; novel dollars fail the lock)
- [ ] `explain` does not call news search
- [ ] Streamlit shows the banner and essay in the same window as structured turns
- [ ] Offline test injects a fake essay completer; default suite does not call OpenAI
