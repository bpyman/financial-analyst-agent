# 05 — Explain with numeral lock E2E

**What to build:** An analyst can ask how AI can disrupt healthcare and get a labeled model-analysis essay with no retrieval and no invented numbers. Structured turns still render as tables; this path is the essay renderer plus numeral lock.

**Blocked by:** 01 — Quarterly lookup E2E

**Status:** resolved

- [x] `run_turn` on an industry/AI explain prompt returns `explain`, essay renderer, and a model-analysis banner
- [x] Essay contains no numeric tokens that were not in tool JSON (explain has no numeric tools; novel dollars fail the lock)
- [x] `explain` does not call news search
- [x] Streamlit shows the banner and essay in the same window as structured turns
- [x] Offline test injects a fake essay completer; default suite does not call OpenAI

## Comments

- Gold tests go through `run_turn` with an injected essay completer or the fixture runtime (`pytest` default excludes `network`).
- Numeral lock compares essay tokens to serialized tool traces. `explain_topic` traces carry the topic only, so invented dollars refuse.
- Streamlit already shows banners via `st.info`; essay renderer adds `st.markdown` in the same window as tables.

## Answer

`run_turn` on “How can AI disrupt healthcare?” returns `explain`, an essay renderer, and a `model-analysis` banner. There is no news search. Novel dollar amounts fail the numeral lock. Streamlit shows the banner and essay beside structured turns. Default tests inject a fake essay completer and do not call OpenAI.
