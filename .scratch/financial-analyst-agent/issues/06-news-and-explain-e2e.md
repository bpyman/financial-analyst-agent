# 06 — News-and-explain E2E

**What to build:** An analyst can ask about a named company’s current situation (e.g. NVIDIA supply chain) and get an essay grounded only in Tavily search hits (title, URL, snippet; date when present), or a refuse if hits are missing/unusable. This is a backup prompt, not one of the three live script items.

**Blocked by:** 05 — Explain with numeral lock E2E

**Status:** ready-for-agent

- [ ] `run_turn` on a named-company current-event query returns `news_and_explain`; `search_news` runs with the user query (`topic=news`, max 5, title+URL required)
- [ ] Essay uses only returned hits; numeral lock allows numbers that appear in that JSON; empty hits refuse rather than using training data
- [ ] Tavily extract/map/crawl are not graph-callable; DuckDuckGo/FMP ticker-only news are not this tool
- [ ] Streamlit shows citation cards (URL/date) plus the essay
- [ ] Offline gold uses a fake news adapter; live Tavily is optional behind the same tool
