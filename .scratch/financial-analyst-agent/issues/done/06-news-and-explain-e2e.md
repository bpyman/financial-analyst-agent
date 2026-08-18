# 06 — News-and-explain E2E

**What to build:** An analyst can ask about a named company’s current situation (e.g. NVIDIA supply chain) and get an essay grounded only in Tavily search hits (title, URL, snippet; date when present), or a refuse if hits are missing/unusable. This is a backup prompt, not one of the three live script items.

**Blocked by:** 05 — Explain with numeral lock E2E

**Status:** resolved

- [x] `run_turn` on a named-company current-event query returns `news_and_explain`; `search_news` runs with the user query (`topic=news`, max 5, title+URL required)
- [x] Essay uses only returned hits; numeral lock allows numbers that appear in that JSON; empty hits refuse rather than using training data
- [x] Tavily extract/map/crawl are not graph-callable; DuckDuckGo/FMP ticker-only news are not this tool
- [x] Streamlit shows citation cards (URL/date) plus the essay
- [x] Offline gold uses a fake news adapter; live Tavily is optional behind the same tool

## Comments

- Gold tests go through `run_turn` with an injected news adapter or the fixture runtime (`pytest` default excludes `network`).
- Empty or title/URL-less hits refuse before the essay completer runs.
- Live Tavily: `uv run pytest tests/integration/test_live_tavily_news.py -m network`.

## Answer

`run_turn` on an NVIDIA supply-chain query returns `news_and_explain`, runs `search_news` with the user query (`topic=news`, max 5), and numeral-locks the essay to hit JSON. Empty hits refuse. Streamlit shows citation URL/date cards plus the essay. Fixture news is the default offline adapter; live Tavily is optional behind the same port.
