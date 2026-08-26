# Public GitHub financial-analyst bots (25 Aug 2026)

Survey of publicly hosted analyst-style agents and related EDGAR/XBRL tooling. Stars are GitHub page counts from that date unless noted. Trading-framework repos are included as **contrast**, not as architecture peers.

This bot (closed intents, 10-Q companyfacts, Decimal formulas, universe-snapshot ranking, numeral lock) is the baseline. Almost none of the surveyed READMEs combine those properties.

## Twelve examples

| Repo | Stars (approx) | Role |
|------|----------------|------|
| [dgunning/edgartools](https://github.com/dgunning/edgartools) | ~2.6k | XBRL/EDGAR library + MCP; not a chat bot |
| [run-llama/sec-insights](https://github.com/run-llama/sec-insights) | ~2.6k | Production 10-K/10-Q RAG + Polygon tools; citations/PDF viewer |
| [ginlix-ai/LangAlpha](https://github.com/ginlix-ai/LangAlpha) | ~1.7k | LangGraph ReAct, provenance UI, SEC/FMP/Yahoo/news |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | ~99k | Multi-agent debate; trade/decide, not provenance-first 10-Q lookup |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | ~63k | Alpha-model crew; Financial Datasets API |
| [stefanoamorelli/sec-edgar-mcp](https://github.com/stefanoamorelli/sec-edgar-mcp) | ~351 | EDGAR MCP, XBRL statements, 8-K, filing URLs |
| [ralliesai/tenk](https://github.com/ralliesai/tenk) | ~134 | CLI RAG over 10-K/10-Q, multi-filing compare (LLM numbers) |
| [twCarllin/10k-analysis](https://github.com/twCarllin/10k-analysis) | ~47 | Deep 10-Q/XBRL pipeline + eval; LLM-heavy reports |
| [gsaini/financial-research-analyst-agent](https://github.com/gsaini/financial-research-analyst-agent) | ~46 | Streamlit multi-agent kitchen sink (DCF, peers, Yahoo/FMP) |
| [bcastelino/sec-filing-room](https://github.com/bcastelino/sec-filing-room) | ~1 | Closest architecture: Company Facts + narrative RAG + citations |
| [nolancacheux/Rag-Equity-Research-Agent](https://github.com/nolancacheux/Rag-Equity-Research-Agent) | ~19 | LangGraph 10-K RAG + peers + Yahoo |
| [finos-labs/Agent-QuickStart](https://github.com/finos-labs/Agent-QuickStart) | ~6 | FINOS notebooks: RAG + guardrails/eval |

Honorable mention (not in the twelve): [stefanoamorelli/sec-edgar-agentkit](https://github.com/stefanoamorelli/sec-edgar-agentkit) (~11) wraps sec-edgar-mcp in LangChain/Gradio; [Sapan2003/Earnings-Call-Analyzer](https://github.com/Sapan2003/Earnings-Call-Analyzer) and [frankwuyue/10K-Filings-Analyzer](https://github.com/frankwuyue/10K-Filings-Analyzer) are simpler Streamlit 10-K RAG apps.

## Feature comparison (vs this bot)

**This bot already has:** closed intents (lookup, compare, rank, rank-and-lookup, explain, news-and-explain); SEC XBRL duration facts; Decimal formulas (no LLM math); operating-company universe freeze; rank-and-lookup composition; numeral lock on news essays.

**Common among the twelve:** open ReAct or RAG over HTML/PDF; Yahoo/FMP/Polygon as the number path; 10-K RAG; citation UIs; peer lists from live screeners.

**Rare or absent:** Decimal compare; snapshot ranking; rank-and-lookup; numeral lock; closed intents with recorded adapters.

**Closest peer:** `sec-filing-room` (Company Facts + citations) but without freeze ranking or numeral lock.

## Curated ideas (ADR-compatible)

1. Annual 10-K lookup on the same fact path as 10-Q.
2. Same-issuer sequential / YoY compare as Decimal math (no YTD subtraction).
3. Instant balance-sheet ratios from companyfacts.
4. Snapshot-member peers then lookup (freeze membership, not a live screener).
5. Filing MD&A explain with citations and numeral lock (HTML, not PDF-as-truth).
6. Labeled vendor TTM column beside the 10-Q fact (never replacing XBRL).
7. 8-K headlines as a current-event tool that can refuse.

**Leave on the table:** open ReAct, LLM arithmetic/DCF, replacing companyfacts with edgartools or FMP ratios, trading/paper portfolios.

## Sources

GitHub READMEs and repo pages fetched or summarized 25 Aug 2026. TradingAgents and ai-hedge-fund star counts from GitHub pages via Tavily the same day.
