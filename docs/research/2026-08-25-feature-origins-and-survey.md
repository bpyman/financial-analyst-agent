# Feature origins and public financial-analyst-agent survey

**Date:** 25 August 2026  
**Baseline:** the local `financial-analyst-agent` v2 product  
**Evidence policy:** primary sources only

## Executive conclusion

The public projects divide into three useful groups:

1. **SEC data primitives** — EdgarTools and SEC EDGAR MCP expose broad filing,
   XBRL, ownership, and disclosure surfaces. They are useful sources of feature
   vocabulary, but their number-selection and arithmetic contracts are not
   automatically interchangeable with v2's stricter standalone-quarter selector.
2. **Filing research workspaces** — SEC Insights, Filing Room, tenk, and the
   10-K/10-Q pipelines demonstrate document scope, citation navigation, exports,
   disclosure review, and long-running research UX. Filing Room is the closest
   architectural peer because it explicitly separates deterministic Company Facts
   calculations from narrative retrieval.
3. **Open financial agents and trading systems** — LangAlpha, Dexter, TradingAgents,
   AI Hedge Fund, and the broad multi-agent projects offer strong workflow and UI
   ideas: persistent workspaces, source panels, visible progress, approvals,
   argument matrices, alerts, and run records. Their open-ended agency, vendor
   number paths, LLM calculations, or trading objectives are not suitable to copy
   into v2's financial-truth boundary.

The strongest new product opportunities are not “more agent autonomy.” They are
better analyst control and inspection around deterministic facts:

- an exact-source evidence inspector;
- a deterministic disclosure-change map;
- an XBRL footnote and statement-reconciliation lens;
- a structured SEC ownership ledger; and
- an audit-ready evidence export bundle.

Those ideas deepen v2 without moving facts, arithmetic, identity, or workflow
selection into the model.

## Scope and method

### Baseline reviewed first

The following local primary documents define v2 and were read before surveying
external projects:

- `prd.md`
- `docs/design.md`
- `CONTEXT.md`
- `docs/research/2026-08-25-github-financial-analyst-bots.md`

The baseline already includes:

- six closed intents: lookup, compare, rank, rank-and-lookup, explain, and
  news-and-explain;
- SEC Company Facts selection for directly reported standalone 10-Q duration
  facts;
- CIK-owned company identity and share-class consolidation;
- deterministic `Decimal` formulas with period-alignment checks;
- a dated operating-company snapshot for reproducible rankings;
- typed partial failures, clarification, and refusal;
- structured tables rendered from tool output rather than rewritten by an LLM;
- a model-analysis boundary and numeral lock for qualitative essays;
- visible intent, tool traces, provenance, and labeled fixture mode; and
- one application contract, `run_turn(query, runtime)`.

### Ideas already present in v2 or its development-origin notes

The ten recommendations later in this report deliberately exclude or materially
go beyond these already-recorded ideas:

- annual 10-K facts on the same fact path;
- same-issuer sequential or year-over-year numeric comparisons;
- instant balance-sheet ratios;
- snapshot-member peer selection followed by fact lookup;
- filing MD&A explanation with citations and numeral lock;
- a labeled vendor TTM column beside SEC facts;
- 8-K headlines as a current-event tool;
- PDF verification against XBRL;
- a broader metric catalog;
- provider caching, retries, rate limiting, freshness monitoring, and observability;
- authentication, authorization, and audit logging;
- routing, identity, fact-selection, and refusal evaluation sets;
- durable workflow state where human approval is useful; and
- open ReAct, model arithmetic/DCF, trading, or paper portfolios, which prior notes
  explicitly leave off the product path.

### External evidence rules

- Repository metadata came from GitHub's repository and commit APIs on
  25 August 2026.
- README, docs, notebooks, source, tests, and checked-in asset paths are first-party
  repository materials.
- Source links below are pinned to the reviewed commit, not a moving `main` branch.
- “README claim” means the repository states a capability but this review did not
  verify its execution path.
- “Verified in source/UI” means an implementation or interface component was
  inspected.
- No blog posts, star aggregators, review articles, or other secondary sources were
  used.

### Screenshot, GIF, and deployed-demo limitations

Checked-in image/GIF paths and README captions were inventoried. This environment
could not render binary GitHub assets in the available browser during the review,
so no pixel-level claim is made from PNG, JPG, GIF, or MP4 content alone. UI
observations below are grounded in inspected React, Streamlit, Textual, or terminal
source unless explicitly labeled as a README caption.

Official demos were considered only when linked by the repository. SEC Insights
links `secinsights.ai`; LangAlpha links its hosted platform for selected features.
Neither deployed application was used as evidence here because an interactive
browser was unavailable. EdgarTools' checked-in demo GIF/MP4, tenk's
`static/demo.gif`, LangAlpha's eight `docs/images/*.png` screenshots,
RAG Equity Research Agent's dashboard/GIF, TradingAgents' four CLI PNGs, and the
SEC EDGAR MCP attachment video are therefore recorded as inaccessible visual
evidence rather than silently inferred.

## Source-by-source inventory

## 1. `dgunning/edgartools`

**Role:** typed SEC/EDGAR and XBRL library with an MCP layer, not primarily an
analyst chat application.  
**GitHub snapshot:** 2,617 stars; reviewed commit
[`aeb15ba`](https://github.com/dgunning/edgartools/tree/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e).

### README and documentation claims

The README advertises typed objects for more than 20 filing types, standardized
financial statements, Company Facts time series, filing-section extraction,
ownership forms, full-text search, caching, an MCP server, and LLM-ready text.
The MCP reference documents 13 intent-shaped tools covering company research,
search, screening, live filing monitoring, filing parsing, section reading,
notes, trends, comparisons, ownership, funds, and proxy statements.

Primary evidence:

- [README](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/README.md)
- [MCP tools reference](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/docs/ai/mcp-tools.md)
- [Architecture diagram](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/docs/architecture-diagram.md)

### Verified source and interface evidence

- `edgar_notes` retrieves a typed 10-K/10-Q note, records which statement lines
  it expands, returns child-table metadata, and can include DataFrame rows at the
  full detail level. This is stronger than generic vector search because the note
  is attached to filing structure.
- The XBRL parser models fact-to-footnote and footnote-to-fact links, including
  footnote IDs, text, role, language, and related fact IDs.
- `edgar_ownership` has separate paths for Form 4 insider activity, current 13F
  portfolios, and quarter-over-quarter 13F portfolio changes. The source explicitly
  rejects the unsupported reverse lookup “which institutions hold this stock,” a
  useful example of bounded product semantics.
- `edgar_monitor` reads the current SEC filing feed and allows a closed form filter.
- Output formats include typed Python objects, DataFrames, dictionaries, Markdown,
  and Rich tables. The repository contains a demo GIF and MP4, but no reviewed
  end-user web application.

Primary evidence:

- [`edgar_notes` implementation](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/edgar/ai/mcp/tools/notes.py)
- [XBRL footnotes guide](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/docs/guides/xbrl-footnotes.md)
- [`edgar_ownership` implementation](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/edgar/ai/mcp/tools/ownership.py)
- [`edgar_monitor` implementation](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/edgar/ai/mcp/tools/monitor.py)
- [Checked-in demo GIF](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/docs/images/edgartools-demo.gif)

### Fit and caveat for v2

The notes, ownership, proxy, and monitor surfaces are excellent feature
inspiration. EdgarTools must not replace v2's reviewed quarterly selector by
default: its API intentionally supports annual, quarterly, and TTM views and broad
statement standardization, while v2 requires a directly reported standalone
quarter and refuses ambiguity. Any integration should consume typed filing
structure behind a v2-owned selection contract.

## 2. `run-llama/sec-insights`

**Role:** full-stack 10-K/10-Q RAG reference application.  
**GitHub snapshot:** 2,608 stars; reviewed commit
[`a9b6da0`](https://github.com/run-llama/sec-insights/tree/a9b6da0f5c4bff52437a5285954ff17bc713f14f).

### README claims

The README claims document Q&A, citations, a PDF viewer with highlighted
citations, Polygon-backed quantitative tools, token streaming, streamed
subquestions, share links, production/preview environments, monitoring, load
testing, and LLM observability. It links the official `secinsights.ai` deployment.

Primary evidence:

- [README](https://github.com/run-llama/sec-insights/blob/a9b6da0f5c4bff52437a5285954ff17bc713f14f/README.md)

### Verified source/UI evidence

- The conversation page is desktop-oriented and composes a conversation pane with
  a multi-PDF viewer. It fetches an existing conversation and selected documents,
  then consumes message updates over `EventSource`.
- The PDF area shows one document at a time with selectable 80×80 document tiles
  labeled by ticker, year, and quarter.
- Citation controls carry ticker, display date, page number, and snippet. Clicking
  a citation updates PDF focus with document ID, page number, and citation data.
- The answer pane has an expandable “View progress” section. It shows “Question
  Received,” generated subqueries, each subquery's answer and citations, and a
  spinner while work continues.
- Suggested first questions are visible as pills. Assistant answers end with an
  informational-purpose disclaimer.
- The code explicitly refuses mobile use on the conversation page.

Primary evidence:

- [Conversation page](https://github.com/run-llama/sec-insights/blob/a9b6da0f5c4bff52437a5285954ff17bc713f14f/frontend/src/pages/conversation/%5Bid%5D.tsx)
- [Conversation and citation renderer](https://github.com/run-llama/sec-insights/blob/a9b6da0f5c4bff52437a5285954ff17bc713f14f/frontend/src/components/conversations/RenderConversations.tsx)
- [Multi-PDF selector](https://github.com/run-llama/sec-insights/blob/a9b6da0f5c4bff52437a5285954ff17bc713f14f/frontend/src/components/pdf-viewer/DisplayMultiplePdfs.tsx)
- [PDF viewer component](https://github.com/run-llama/sec-insights/blob/a9b6da0f5c4bff52437a5285954ff17bc713f14f/frontend/src/components/pdf-viewer/ViewPdf.tsx)
- [Checked-in full-chat asset](https://github.com/run-llama/sec-insights/blob/a9b6da0f5c4bff52437a5285954ff17bc713f14f/frontend/public/full-chat.png)

### Fit and caveat for v2

The citation-to-document interaction is the main transferable idea. Its
quantitative path is provider-tool based and its document answers are generated;
neither should be allowed to overwrite v2's XBRL fact or deterministic renderer.
The current code's open subquestion flow should be adapted as visibility into a
closed executor, not copied as open workflow planning.

## 3. `ginlix-ai/LangAlpha`

**Role:** broad financial agent workbench with persistent sandboxes, tools,
artifacts, automations, and subagents.  
**GitHub snapshot:** 1,692 stars; reviewed commit
[`d238327`](https://github.com/ginlix-ai/LangAlpha/tree/d2383272b2b5a03965b82ad1ca6df986bfeb7854).

### README claims

LangAlpha describes research as a persistent, iterative workspace rather than
one-shot chat. It claims programmatic tool calling in sandboxes, native and MCP
financial-data tiers, inline charts, file viewers, per-turn provenance, shareable
conversations, subagent monitoring, live steering, scheduled and price-triggered
automations, workspace memory, source-aware skills, and multiple delivery channels.

The README's checked-in screenshots are captioned as:

- a market/news/watchlist dashboard;
- a dashboard preset picker;
- a widget gallery;
- a support/resistance MarketView analysis;
- a workspace list;
- a data-center/AI-compute timeline;
- a catalyst-calendar dashboard; and
- an NVDA/AMD/GOOGL comps/implied-valuation view.

Those captions establish intended interface scope, but the binary screenshots
were not visually rendered in this review.

Primary evidence:

- [README](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/README.md)
- [Checked-in UI images](https://github.com/ginlix-ai/LangAlpha/tree/d2383272b2b5a03965b82ad1ca6df986bfeb7854/docs/images)

### Verified source/UI evidence

- The source panel has a “This turn / All sources” scope. It groups provenance
  records by source type and supports web search, web fetch, SEC filing, market
  data, MCP tool, file, memo, and memory records.
- URL sources receive domain-aware grouping and favicons. File-like sources route
  into the workspace file viewer. Tool arguments are surfaced as key/value
  summaries; server redaction sentinels remain visibly redacted.
- The panel distinguishes the number of distinct source URLs from grouped rows,
  avoiding a wall of repeated sources from one search or domain.
- The automation execution-history table displays status, linked thread, scheduled
  time, duration, and error.
- The subagent status bar presents running/completed/cancelled/error states,
  current tool, tool-call count, and the failure reason. It accepts steering
  instructions only while a task is non-terminal.
- The detail panel opens plan details, tool-call details, file artifacts, or
  subagent tasks.

Primary evidence:

- [Sources panel](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/web/src/pages/ChatAgent/components/SourcesPanel.tsx)
- [Tool/plan detail panel](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/web/src/pages/ChatAgent/components/DetailPanel.tsx)
- [Subagent status bar](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/web/src/pages/ChatAgent/components/SubagentStatusBar.tsx)
- [Automation execution history](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/web/src/pages/Automations/components/ExecutionHistoryTable.tsx)

### Fit and caveat for v2

LangAlpha is the richest UI/workspace inspiration and the wrong correctness
architecture to copy wholesale. Its agent writes code and autonomously discovers
tools across FMP, Yahoo, Polygon, web, and MCP layers. V2 should borrow source
organization, artifacts, and execution history while retaining closed workflows
and v2-owned identities, periods, formulas, and rendered facts.

## 4. `stefanoamorelli/sec-edgar-mcp`

**Role:** SEC-focused MCP server built on `sec-edgar-toolkit`.  
**GitHub snapshot:** 351 stars; reviewed commit
[`88b21ad`](https://github.com/stefanoamorelli/sec-edgar-mcp/tree/88b21ad58c24ad9ab9be21e093d71571457b9057).

### README/docs claims

The project claims company, filing, financial-statement, XBRL-concept, and insider
tools with exact precision and SEC verification URLs. It supports stdio and
streamable HTTP and explicitly warns that HTTP transport includes no
authentication.

Primary evidence:

- [README](https://github.com/stefanoamorelli/sec-edgar-mcp/blob/88b21ad58c24ad9ab9be21e093d71571457b9057/README.md)
- [Tools overview](https://github.com/stefanoamorelli/sec-edgar-mcp/blob/88b21ad58c24ad9ab9be21e093d71571457b9057/docs/tools/overview.mdx)
- [Financial-analysis use cases](https://github.com/stefanoamorelli/sec-edgar-mcp/blob/88b21ad58c24ad9ab9be21e093d71571457b9057/docs/use-cases/financial-analysis.mdx)

### Verified source evidence and claim gap

- The source provides latest-filing statements, segment extraction, Company Facts
  metrics, period comparison, concept discovery, and specific-concept extraction.
- It returns filing form, date, accession, and a filing reference on several paths.
- Insider tools enumerate Forms 3/4/5, parse Form 4 owners, transactions, and
  holdings, and retain filing URLs/accessions.
- The “exact precision/no rounding” documentation is not true for every
  implementation path. `get_key_metrics` converts filed values to `float`;
  period comparison also stores floats, computes growth with floating-point
  arithmetic, and rounds percentages to two decimals. Segment extraction accepts
  `int | float`. This is a concrete reason not to inherit the server's precision
  claim as a v2 contract.

Primary evidence:

- [Financial tools source](https://github.com/stefanoamorelli/sec-edgar-mcp/blob/88b21ad58c24ad9ab9be21e093d71571457b9057/sec_edgar_mcp/tools/financial.py)
- [Insider tools source](https://github.com/stefanoamorelli/sec-edgar-mcp/blob/88b21ad58c24ad9ab9be21e093d71571457b9057/sec_edgar_mcp/tools/insider.py)

### UI observation and fit

This is a tool server, not a standalone analyst UI. The README includes an
attachment video, but it was inaccessible for visual inspection. V2 can borrow
tool taxonomy and SEC links, not the precision claim or latest-value selection.
Its unauthenticated HTTP warning reinforces v2's decision to keep local HTTP
private unless a later deployment adds an authenticated gateway.

## 5. `ralliesai/tenk`

**Role:** terminal RAG application over downloaded 10-K/10-Q filings.  
**GitHub snapshot:** 134 stars; reviewed commit
[`a71a1b8`](https://github.com/ralliesai/tenk/tree/a71a1b847efdab0c9c9165483afac7fa23b01503).

### README claims

The README claims local filing indexing, multi-filing questions, citations,
Yahoo stock data, web search, Code Interpreter, conversation memory, Excel
generation, and PDF/DOCX/Excel exports.

Primary evidence:

- [README](https://github.com/ralliesai/tenk/blob/a71a1b847efdab0c9c9165483afac7fa23b01503/README.md)
- [Checked-in demo GIF](https://github.com/ralliesai/tenk/blob/a71a1b847efdab0c9c9165483afac7fa23b01503/static/demo.gif)

### Verified source/UI evidence and claim gap

- The terminal prints each tool name and compact arguments, then a truncated
  output preview. Generated text streams inside a bordered Rich Markdown panel.
- After an answer, export choices appear at the right: PDF and DOCX always, Excel
  only if a Markdown table is detected.
- PDF and DOCX are generated from answer Markdown. Excel creates one worksheet per
  Markdown table with basic styles and column widths.
- The source passes open web search and Code Interpreter to the filing analyst.
- Most importantly, `run_query` applies `strip_citations` to the streamed display
  and to the returned `answer_text`; exports are produced from that stripped text.
  The README's citation claim may apply inside model/tool content, but the reviewed
  terminal/export path deliberately removes citation markers. It is therefore not
  an audit-ready export implementation.

Primary evidence:

- [Agent loop](https://github.com/ralliesai/tenk/blob/a71a1b847efdab0c9c9165483afac7fa23b01503/src/agent.py)
- [Terminal UI](https://github.com/ralliesai/tenk/blob/a71a1b847efdab0c9c9165483afac7fa23b01503/src/terminal.py)
- [Export implementation](https://github.com/ralliesai/tenk/blob/a71a1b847efdab0c9c9165483afac7fa23b01503/src/export.py)

### Fit and caveat for v2

The compact tool-call UI and answer-adjacent exports are useful. V2 must export
typed tool results and evidence, not generated Markdown with citations removed.
Code Interpreter and LLM-authored financial models violate v2's arithmetic
boundary.

## 6. `twCarllin/10k-analysis`

**Role:** long-running US and Japan filing/transcript research pipeline with
specialized analysis prompts.  
**GitHub snapshot:** 47 stars; reviewed commit
[`0d5e604`](https://github.com/twCarllin/10k-analysis/tree/0d5e604e9d81142d8698cb42b42b7daa94053af4).

### README claims

The project claims US SEC and Japan EDINET/TDNET pipelines, earnings-call
transcripts, parallel analysis stages, prior-period synthesis, hard-rule/schema/
LLM evaluation, retry hints, checkpoints, context/cost logs, and Markdown/PDF/raw
JSON output. It has no web UI.

Primary evidence:

- [README](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/README.md)
- [Orchestrator](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/runtime/orchestrator.py)

### Verified analysis definitions

- `three_statement_cross` asks for revenue, receivables, inventory, CapEx,
  operating cash flow, and free cash flow trends, then classifies revenue/cash,
  profit/revenue, CapEx effectiveness, and inventory/cash-flow relationships.
- `unusual_operations` searches footnote and financial-analysis candidates for
  securitization, factoring, sale-leaseback, VIE, off-balance-sheet, revenue
  recognition, and similar patterns. It requires source quotes and a stated
  financial impact.
- Checkpoint/resume and per-agent context logging are real pipeline concepts in
  source.

Primary evidence:

- [Three-statement cross-check skill](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/skills/three_statement_cross.md)
- [Unusual-operations skill](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/skills/unusual_operations.md)
- [Pipeline state](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/runtime/pipeline_state.py)
- [Evaluation runner](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/runtime/eval_runner.py)

### Trust-boundary gap

The cross-statement and unusual-operation logic is written as LLM skill
instructions, including calculations, classification, and investment
interpretation. XBRL is an input, but the model is still asked to calculate and
judge. V2 should adopt only rule definitions that can be re-expressed as typed
`Decimal` calculations and explicitly cited disclosure matches. “CapEx caused
future revenue” and “industry norm” are interpretive claims and must remain
labeled analysis.

## 7. `gsaini/financial-research-analyst-agent`

**Role:** very broad Streamlit/FastAPI/CLI multi-agent suite.  
**GitHub snapshot:** 46 stars; reviewed commit
[`d6fe4fd`](https://github.com/gsaini/financial-research-analyst-agent/tree/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d).

### README claims

The README lists 11 agents, numerous market and portfolio analytics, RAG,
multi-provider fallback, DCF, forecasting, portfolio optimization, reports,
alerts, themes, peer comparison, disruption analysis, and a multi-page
Streamlit dashboard.

Primary evidence:

- [README](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/README.md)

### Verified source/UI evidence

- The checked-in frontend contains 17 numbered pages, including dashboard, stock
  analysis, themes, peers, disruption, earnings, portfolios, reports, news,
  performance, sentiment, ETF screening, macro, short interest, dividends,
  analyst consensus, and alerts.
- Alert UI has “Create Alert,” “Active Alerts,” and “Triggered History” tabs.
  It dynamically labels thresholds, offers quick presets, supports repeating
  alerts, and displays a tabular trigger history.
- Alert evaluation is deterministic code for price, percent move, volume, RSI,
  MACD, moving-average crosses, 52-week levels, earnings dates, ex-dividend dates,
  and short interest. However, it uses vendor market data and in-memory storage;
  the UI explicitly says alerts reset on server restart.
- PDF and Excel exports are implemented, but they serialize broad analysis
  dictionaries and recommendations without a provenance manifest. The PDF can
  include AI recommendations and DCF outputs, which are outside v2's boundary.

Primary evidence:

- [Alerts page](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/frontend/pages/17_Alerts.py)
- [Alert engine](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/src/tools/alerts.py)
- [Report export](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/src/tools/report_export.py)
- [Frontend page tree](https://github.com/gsaini/financial-research-analyst-agent/tree/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/frontend/pages)

### Fit and caveat for v2

The alert-center information architecture is useful. The overall product is a
kitchen sink and its Yahoo/FMP/Alpha Vantage values, model recommendations, DCF,
forecasting, and portfolio outputs should not enter v2's reported-quarter path.

## 8. `bcastelino/sec-filing-room`

**Role:** scoped SEC research workspace combining deterministic Company Facts
calculations with filing retrieval.  
**GitHub snapshot:** 1 star; reviewed commit
[`de0a4ad`](https://github.com/bcastelino/sec-filing-room/tree/de0a4ad6b51aa18372180da811cb030895a73735).

### README claims

Filing Room presents itself as “Ask the filing. Trace the answer.” It claims a
React research workspace, one-to-three-company scope, form/year selection,
deterministic Company Facts growth and margins, structured filing chunks,
validated citations, source excerpts, direct SEC links, browser-local history,
CSV export, and streamed status/answers.

It also clearly marks limitations: Cloudflare deployment has not been performed;
Vectorize retrieval/reranking is not fully connected; comparison export is a
prototype; and fixture/evaluation coverage needs expansion.

Primary evidence:

- [README](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/README.md)
- [Methodology](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/docs/methodology.md)

### Verified source/UI evidence

- The research scope drawer accepts up to three CIK-deduplicated companies,
  10-K/10-Q forms, and up to five fiscal years. The active scope is summarized
  in the top bar.
- The empty state suggests risks, year-over-year change, and revenue-growth
  comparison questions.
- Streamed status changes from searching selected filings to an accession-aware
  preparation message and finally “Answer grounded in selected SEC filings.”
- Citation markers resolve only against the returned source list. Selecting one
  opens a right-side source inspector showing ticker, form, filed date, section,
  exact excerpt, accession, source ID, and “Open original filing.”
- Local history is explicitly “Stored only in this browser.” Shared URLs carry
  scope and a question, not generated answers.
- The current retriever applies company/form/year/accession/section filters before
  lexical scoring and emits bounded 1,200-character excerpts with SEC URLs.
- The metric chart shows a filing-history line chart and current compact value.
  Its presentation helper uses JavaScript `number` and formatted billions; it is
  presentation inspiration, not an authoritative precision path.

Primary evidence:

- [Research page](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/web/src/pages/ResearchPage.tsx)
- [Citation renderer](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/web/src/components/CitationText.tsx)
- [Metric chart](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/web/src/components/MetricChart.tsx)
- [Retriever](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/api/filing_room/retrieval.py)

### Fit and caveat for v2

This is the closest product peer. Its source inspector and explicit research
scope can be adapted nearly directly at the presentation level. V2 should retain
its own stricter quarterly selector, snapshot ranking, closed intents, and
numeral lock. Filing Room's generated narrative path does not by itself provide
v2's numeric-token constraint.

## 9. `nolancacheux/Rag-Equity-Research-Agent`

**Role:** LangGraph equity-research pipeline with SEC RAG, market data, peers,
sentiment, Telegram, and REST interfaces.  
**GitHub snapshot:** 19 stars; reviewed commit
[`8db4c79`](https://github.com/nolancacheux/Rag-Equity-Research-Agent/tree/8db4c797c074114faf71d330a5982ebb2e5acbab).

### README/docs claims

The README claims real-time Yahoo metrics, hybrid SEC RAG, earnings-call analysis,
news and Reddit sentiment, peer comparison, risk scoring, report generation,
Telegram, FastAPI, Qdrant, and Azure deployment. Checked-in visual assets include
an Azure dashboard PNG and a demonstration GIF; neither could be rendered here.

Primary evidence:

- [README](https://github.com/nolancacheux/Rag-Equity-Research-Agent/blob/8db4c797c074114faf71d330a5982ebb2e5acbab/README.md)
- [Checked-in demo assets](https://github.com/nolancacheux/Rag-Equity-Research-Agent/tree/8db4c797c074114faf71d330a5982ebb2e5acbab/demo)

### Verified source evidence

- The peer agent returns a typed structure containing peers, per-metric values,
  ranking, strengths, weaknesses, summary, and errors.
- Peer membership is mostly a manually curated ticker dictionary. Unknown tickers
  fall into a stub sector-discovery method that currently returns an empty list.
- Metrics are Yahoo price, P/E, and market cap. Rankings and percentiles use Python
  floats, and prose such as “Best P/E” is generated from those vendor values.
- The architecture's peer-comparison claim is therefore narrower and less dynamic
  than the README wording may suggest.

Primary evidence:

- [Peer agent](https://github.com/nolancacheux/Rag-Equity-Research-Agent/blob/8db4c797c074114faf71d330a5982ebb2e5acbab/src/agents/peer_agent.py)
- [Peer service](https://github.com/nolancacheux/Rag-Equity-Research-Agent/blob/8db4c797c074114faf71d330a5982ebb2e5acbab/src/services/peer_comparison.py)
- [Hybrid RAG documentation](https://github.com/nolancacheux/Rag-Equity-Research-Agent/blob/8db4c797c074114faf71d330a5982ebb2e5acbab/docs/embeddings-rag.md)

### Fit and caveat for v2

Typed peer rows and partial errors are compatible concepts, but v2 already has a
stronger snapshot-based peer/rank direction in prior ideas. Yahoo values and
manual ticker groups must not become v2 identity or membership truth.

## 10. `finos-labs/Agent-QuickStart`

**Role:** FINOS educational notebooks demonstrating multiple agent frameworks,
financial RAG, safety, and evaluation.  
**GitHub snapshot:** 6 stars; reviewed commit
[`7e83fd6`](https://github.com/finos-labs/Agent-QuickStart/tree/7e83fd6e32edcbf3a9206e9a8b66342f08600f29).

### README claims

The README describes a metacognitive financial advisor, SEC filing RAG,
stock/sentiment analysis, and a FinSight earnings-call workflow. It emphasizes
confidence thresholds, source verification, operating boundaries, professional
referral, guardrail tracking, and DeepEval.

Primary evidence:

- [README](https://github.com/finos-labs/Agent-QuickStart/blob/7e83fd6e32edcbf3a9206e9a8b66342f08600f29/README.md)

### Verified notebook evidence and claim gap

- `finsight_agent.ipynb` defines typed sentiment, event, transcript-answer, and
  volatility outputs with model-supplied confidence fields.
- It defines a self-model with per-agent confidence thresholds, operating
  boundaries, source verification, and investment-advice prohibitions.
- Event outputs contain `verified` and `source` fields, but those are populated
  through an LLM structured response.
- The execution state initializes `guardrails_applied` as an empty list. The final
  report counts that list, while a later display cell compares confidence values
  to thresholds. In the reviewed cells, the graph does not enforce a hard stop or
  filter at those thresholds. “Guardrail tracking” is therefore partly modeled
  and displayed rather than a demonstrated deterministic control.

Primary evidence:

- [FinSight notebook](https://github.com/finos-labs/Agent-QuickStart/blob/7e83fd6e32edcbf3a9206e9a8b66342f08600f29/finsight_agent.ipynb)
- [SEC/LlamaIndex notebook](https://github.com/finos-labs/Agent-QuickStart/blob/7e83fd6e32edcbf3a9206e9a8b66342f08600f29/llama_index_agent_example.ipynb)
- [Metacognitive advisor notebook](https://github.com/finos-labs/Agent-QuickStart/blob/7e83fd6e32edcbf3a9206e9a8b66342f08600f29/langgraph_agent_example.ipynb)

### Fit and caveat for v2

Visible boundaries are valuable, but model-reported confidence is not a truth
metric. V2 should expose deterministic coverage checks—facts present, periods
aligned, citations resolvable, numerals grounded—rather than turn an LLM's
self-confidence into a release or answer gate.

## 11. `TauricResearch/TradingAgents`

**Role:** multi-agent trading-research framework and contrast case.  
**GitHub snapshot:** 100,181 stars; reviewed commit
[`a33fd4c`](https://github.com/TauricResearch/TradingAgents/tree/a33fd4c0f134485a43553a2c23a63cb14adbd88f).

### README claims

TradingAgents coordinates fundamental, sentiment, news, and technical analysts;
bull and bear researchers; a trader; risk agents; and a portfolio manager. It
supports checkpoint resume, a persistent decision log, multiple providers, a
terminal UI, and deterministic company-identity/price-snapshot improvements.
The README explicitly acknowledges LLM and live-data non-determinism.

Primary evidence:

- [README](https://github.com/TauricResearch/TradingAgents/blob/a33fd4c0f134485a43553a2c23a63cb14adbd88f/README.md)
- [Checked-in CLI images](https://github.com/TauricResearch/TradingAgents/tree/a33fd4c0f134485a43553a2c23a63cb14adbd88f/assets/cli)

### Verified source/UI evidence

- The CLI source is a large interactive flow for ticker, date, analyst set,
  research depth, provider/model, and result progress.
- The research manager consumes the bull/bear debate history and asks an LLM for a
  structured five-level Buy-to-Sell plan.
- That manager explicitly has no external tools; it judges already-generated
  debate text. Structured output improves shape, not factual correctness.
- Checkpoint and decision-memory modules are real source components.

Primary evidence:

- [CLI source](https://github.com/TauricResearch/TradingAgents/blob/a33fd4c0f134485a43553a2c23a63cb14adbd88f/cli/main.py)
- [Research manager](https://github.com/TauricResearch/TradingAgents/blob/a33fd4c0f134485a43553a2c23a63cb14adbd88f/tradingagents/agents/managers/research_manager.py)
- [Checkpointer](https://github.com/TauricResearch/TradingAgents/blob/a33fd4c0f134485a43553a2c23a63cb14adbd88f/tradingagents/graph/checkpointer.py)
- [Memory source](https://github.com/TauricResearch/TradingAgents/blob/a33fd4c0f134485a43553a2c23a63cb14adbd88f/tradingagents/agents/utils/memory.py)

### Fit and caveat for v2

Trading decisions, portfolio memory, technical analysis, and LLM debate are out of
scope. A non-trading, evidence-structured “arguments for / arguments against /
unknowns” view is transferable if it never produces authoritative numbers or an
action rating.

## 12. `virattt/ai-hedge-fund`

**Role:** educational multi-model fund, backtest, and terminal application;
contrast rather than an SEC analyst peer.  
**GitHub snapshot:** 63,043 stars; reviewed commit
[`eff8a73`](https://github.com/virattt/ai-hedge-fund/tree/eff8a7320fcf0b473b135690fa1a5b0d9b022a83).

### README/roadmap claims

The current product centers on saved fund mandates, configurable strategies,
rebalance cadence, historical backtests, and an interactive terminal. The roadmap
distinguishes shipped, in-progress, and planned work and says a persistent ledger
currently writes run receipts but does not yet seed the next run's book.

Primary evidence:

- [README](https://github.com/virattt/ai-hedge-fund/blob/eff8a7320fcf0b473b135690fa1a5b0d9b022a83/README.md)
- [Roadmap](https://github.com/virattt/ai-hedge-fund/blob/eff8a7320fcf0b473b135690fa1a5b0d9b022a83/ROADMAP.md)

### Verified source/UI evidence

- The Textual app has three explicit screens: a home screen, a two-pane fund
  builder with step rail, and a backtest screen with a live-drawing equity curve.
- The UI writes the same YAML mandate the non-interactive client reads and calls
  the same backtest engine, a good example of multiple interfaces over one core.
- Risk limits are genuinely deterministic: per-position weights are clamped,
  then gross exposure is proportionally scaled. Every clamp records before/after
  values and the limit that fired; removed exposure remains cash.

Primary evidence:

- [Textual application](https://github.com/virattt/ai-hedge-fund/blob/eff8a7320fcf0b473b135690fa1a5b0d9b022a83/hedge_fund/tui/app.py)
- [Deterministic risk limits](https://github.com/virattt/ai-hedge-fund/blob/eff8a7320fcf0b473b135690fa1a5b0d9b022a83/hedge_fund/risk/limits.py)

### Fit and caveat for v2

The clamp audit trail is a useful design analogy: deterministic guards should show
what changed and why. Fund construction, backtesting, and trading are explicitly
outside v2. V2 can borrow the “same engine, multiple thin interfaces” and
before/after guard-event presentation without adding portfolios.

## 13. `virattt/dexter`

**Role:** autonomous terminal agent for broad financial research.  
**GitHub snapshot:** 27,546 stars; reviewed commit
[`ecaed30`](https://github.com/virattt/dexter/tree/ecaed3011f24ea24ef687ab536aa7f22f7294038).

### README claims

Dexter claims task planning, autonomous tools, self-validation, real-time
statements, loop protection, scratchpad traces, evaluation, and WhatsApp access.
This is the most distinctive additional example because it treats traceability and
agent-operability as first-class terminal UX.

Primary evidence:

- [README](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/README.md)

### Verified source/UI evidence

- Every tool event displays a humanized tool name and compact arguments. Active
  calls pulse; completed calls show summary plus duration; failures show a
  truncated error; approval outcomes and limit warnings have distinct states.
- Permission prompts show the tool/action target, optional reason, and choices for
  one-time/session/always authorization or denial.
- The append-only JSONL scratchpad records the original query, tool name,
  arguments, raw result, and thinking entries. It warns on repeated similar calls
  and suggested per-tool limits, preserves full results, and supports context
  compaction without rewriting the log.
- The evaluation terminal displays dataset hash, target and judge models, seed,
  progress, per-question scores, exact passes, contradictions, infrastructure
  failures, tracking errors, and latency by question type.
- Finance tools include statements, ratios, filings, segments, insider trades,
  institutional holdings, and 13D/13G beneficial ownership. Most are backed by
  Financial Datasets rather than direct SEC clients.
- Insider-name resolution runs deterministic token matching first, then an LLM
  fallback whose output is constrained to exact names in a candidate list. This
  is safer than free text but still weaker than v2's fully deterministic identity
  boundary.

Primary evidence:

- [Tool-event UI](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/components/tool-event.ts)
- [Approval prompt](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/components/approval-prompt.ts)
- [Scratchpad](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/agent/scratchpad.ts)
- [Evaluation UI](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/evals/components/eval-app.ts)
- [Insider trades](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/tools/finance/insider_trades.ts)
- [Beneficial ownership](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/tools/finance/beneficial_ownership.ts)
- [Financial segments](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/tools/finance/segments.ts)

### Fit and caveat for v2

Dexter is a strong interface and operations reference, not a financial-truth
reference. V2 should borrow its compact tool lifecycle, immutable trace concept,
and evaluation metadata. It should not borrow autonomous planning, model
self-validation, open shell/web tools, or vendor facts as substitutes for SEC
provenance.

## Cross-source findings

### Features that are common but not differentiating for v2

- Open ReAct or planner-selected tool chains.
- PDF/HTML RAG with generated answers.
- Yahoo/FMP/Polygon/Financial Datasets as the primary number source.
- Multi-agent role decomposition.
- Model-authored confidence scores.
- General PDF/Excel report generation.
- Trading ratings, backtests, and portfolio simulation.

These are popular, but popularity is not evidence that they fit v2's trust
contract.

### Features that are rare and valuable

- A citation that opens the exact source location, not only a URL.
- A deterministic scope control before retrieval.
- Typed source records covering facts, filings, tools, and artifacts.
- Guard events that record before/after values and the reason a rule fired.
- Clear status, errors, and execution metadata for long work.
- A machine-readable, append-only evidence record.
- Honest source-level limitations in the README and UI.

### Repeated claim/source gaps

Several projects use trust language more strongly than their source supports:

- SEC EDGAR MCP claims exact precision while multiple paths convert to `float`.
- tenk claims citations while its reviewed terminal/export path strips citation
  markers.
- FINOS FinSight models guardrails and confidence thresholds, but the reviewed
  graph does not enforce those thresholds as a hard control.
- Broad agent READMEs often say “verified,” “confidence,” or “professional-grade”
  when those fields are generated by the model.
- Multi-agent debate and LLM-as-judge improve process visibility but do not make
  financial facts deterministic.

V2's stronger position is to state narrower guarantees and make the enforcing code
visible.

## Ten genuinely new feature ideas

The following list contains exactly ten ideas. Each is new relative to shipped v2
and the existing/development-origin ideas enumerated earlier.

## Idea 1 — Exact-source evidence inspector

**User value**

An analyst can select any displayed value, citation, or tool trace and inspect the
exact supporting record without leaving the answer context. Verification becomes
a two-second interaction instead of a hunt through an accession or raw JSON.

**Exact repo inspiration**

- Filing Room's right-side inspector with excerpt, accession, section, and original
  filing link.
- SEC Insights' citation-to-document/page focus.
- LangAlpha's per-turn/all-thread source grouping and source-type cards.

**Primary evidence**

- [Filing Room research page](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/web/src/pages/ResearchPage.tsx)
- [Filing Room citation renderer](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/web/src/components/CitationText.tsx)
- [SEC Insights citation renderer](https://github.com/run-llama/sec-insights/blob/a9b6da0f5c4bff52437a5285954ff17bc713f14f/frontend/src/components/conversations/RenderConversations.tsx)
- [LangAlpha source panel](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/web/src/pages/ChatAgent/components/SourcesPanel.tsx)

**UI adaptation for v2**

Add a persistent right drawer opened by a row, provenance badge, or tool card.
For a quarterly fact, show:

- company name, preferred ticker, and CIK;
- metric display name plus taxonomy/concept;
- exact unformatted `Decimal` string and unit;
- form, accession, filing date, period start/end, and duration;
- selection status (“directly reported standalone quarter”);
- SEC Company Facts endpoint and filing URL; and
- related trace ID.

For news or filing narrative, show the exact returned snippet/excerpt and citation
URL. Offer “This answer” and “All evidence in turn,” but not global memory by
default.

**Trust-boundary caveat**

Source IDs and URLs must be created by deterministic adapters and validated
against the turn's evidence set. The model cannot mint citation IDs or arbitrary
SEC URLs. Excerpts are untrusted filing/web content and must be escaped/sanitized.
The drawer must show raw values without introducing JavaScript-number rounding.

**Novelty versus v2**

V2 already shows provenance and expandable tool traces; it does not provide a
unified, exact-source drill-down that connects a rendered cell to its raw fact or
opens a narrative citation in context. This is UI depth, not the already-recorded
MD&A retrieval idea.

## Idea 2 — Deterministic disclosure-change map

**User value**

An analyst can answer “what changed?” across two filings without reading both
documents end to end. Added, removed, and materially edited disclosure blocks are
shown side by side with exact filing anchors.

**Exact repo inspiration**

- Filing Room's deterministic company/form/year scope and “What changed year over
  year?” entry point.
- twCarllin's cross-year, risk, MD&A, and transcript comparison workflow.
- EdgarTools' structured section extraction.

**Primary evidence**

- [Filing Room research scope](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/web/src/pages/ResearchPage.tsx)
- [Filing Room methodology](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/docs/methodology.md)
- [twCarllin pipeline inventory](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/README.md)
- [EdgarTools section reader reference](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/docs/ai/mcp-tools.md)

**UI adaptation for v2**

Add a closed `disclosure_diff` workflow with:

- one CIK, one form family, two explicit accessions;
- reviewed sections such as Risk Factors, MD&A, and Controls;
- section-presence matrix;
- side-by-side blocks with added/removed/changed highlighting;
- deterministic lexical similarity and exact source anchors; and
- optional model summary labeled “analysis of highlighted changes.”

Numbers in the summary remain subject to the evidence numeral lock.

**Trust-boundary caveat**

Document parsing, section identity, accession choice, and text diff are
deterministic. The model may summarize only the produced diff; it cannot decide
which filings or sections count, and it cannot infer that changed wording caused a
financial result. Parser misses and amendments must be visible.

**Novelty versus v2**

The existing sequential/YoY idea compares numeric facts, and the MD&A idea answers
questions within filing text. Neither proposes an accession-pinned narrative
change map with deterministic added/removed/changed blocks.

## Idea 3 — XBRL footnote lens and statement-reconciliation checks

**User value**

An analyst can move from a reported number to the note that explains it and see
typed warnings when related statements move in potentially inconsistent ways.
This supports quality-of-earnings review without asking a model to calculate.

**Exact repo inspiration**

- EdgarTools' fact-linked XBRL footnotes and structured `edgar_notes`.
- twCarllin's three-statement and unusual-operation checklists.
- SEC EDGAR MCP's segment and concept-discovery surfaces.

**Primary evidence**

- [EdgarTools XBRL footnotes](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/docs/guides/xbrl-footnotes.md)
- [EdgarTools notes tool](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/edgar/ai/mcp/tools/notes.py)
- [Three-statement checks](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/skills/three_statement_cross.md)
- [Unusual-operations checks](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/skills/unusual_operations.md)

**UI adaptation for v2**

Add a “Context” tab on a fact:

- linked XBRL footnotes and typed filing notes;
- the statement line(s) the note expands;
- exact source text and table previews;
- deterministic checks such as receivables growth versus revenue growth,
  inventory growth versus revenue growth, operating cash flow versus net income,
  and zero/missing-component states; and
- a guard-event list showing formula, input facts, periods, result, threshold, and
  status (`information`, `watch`, or `not_evaluable`).

**Trust-boundary caveat**

Every ratio and threshold uses `Decimal`, aligned periods, and reviewed concepts.
The system must not assert fraud, causation, “industry norm,” or a bullish/bearish
conclusion. Those are model interpretations at most, clearly separated from the
check result. Footnote relationships are filing evidence, not proof that a note
fully explains a metric.

**Novelty versus v2**

This is not the existing PDF-verification fallback or instant-ratio idea. It adds
fact-linked note navigation and cross-statement guard events with typed evidence.

## Idea 4 — SEC ownership and insider-activity ledger

**User value**

An analyst can inspect recent Form 4 activity, current 13D/13G beneficial owners,
and 13F portfolio changes as structured SEC events instead of reading isolated
filings or accepting a model's “insider sentiment.”

**Exact repo inspiration**

- EdgarTools' Form 4, 13F portfolio, and portfolio-diff tool.
- SEC EDGAR MCP's Form 3/4/5 parsers and accession links.
- Dexter's separate insider-name and 13D/13G query surfaces.

**Primary evidence**

- [EdgarTools ownership tool](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/edgar/ai/mcp/tools/ownership.py)
- [SEC EDGAR MCP insider source](https://github.com/stefanoamorelli/sec-edgar-mcp/blob/88b21ad58c24ad9ab9be21e093d71571457b9057/sec_edgar_mcp/tools/insider.py)
- [Dexter insider trades](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/tools/finance/insider_trades.ts)
- [Dexter beneficial ownership](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/tools/finance/beneficial_ownership.ts)

**UI adaptation for v2**

Add closed ownership subworkflows:

- “Recent insider filings for company”;
- “Current 5% owners for company”;
- “Current 13F portfolio for filer CIK”; and
- “13F changes between adjacent filings.”

Render an event ledger with filer/owner identity, form, filing date, accession,
transaction code, acquired/disposed flag, shares, price if filed, post-transaction
holdings, ownership percentage where applicable, and SEC link. Show amendments as
a chain, not duplicate events.

**Trust-boundary caveat**

CIKs, reporting-owner identity, transaction codes, amendment chains, and
calculations are deterministic. Do not label buys/sells as “sentiment,” predict
price impact, or infer beneficial-owner intent beyond filed 13D/13G categories and
quoted purpose text. Vendor-only coverage is unacceptable for the authoritative
ledger.

**Novelty versus v2**

V2 has company facts, rankings, news, and qualitative explanation but no ownership
forms or event ledger. This is not the prior 8-K-headline idea.

## Idea 5 — Earnings-call claim reconciliation

**User value**

An analyst can see which management claims from an earnings call are supported,
not found, or contradicted by a filed 10-Q/10-K/8-K, with both exact quotes
visible. It turns transcripts into a review queue rather than a second source of
financial truth.

**Exact repo inspiration**

- twCarllin's transcript-plus-filing report split and management-guidance review.
- FINOS FinSight's event-verification fields and official-source intent.
- RAG Equity Research Agent's transcript/SEC combination.

**Primary evidence**

- [twCarllin report structure and transcript pipeline](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/README.md)
- [FINOS FinSight notebook](https://github.com/finos-labs/Agent-QuickStart/blob/7e83fd6e32edcbf3a9206e9a8b66342f08600f29/finsight_agent.ipynb)
- [RAG Equity Research Agent README](https://github.com/nolancacheux/Rag-Equity-Research-Agent/blob/8db4c797c074114faf71d330a5982ebb2e5acbab/README.md)

**UI adaptation for v2**

Use a closed two-column review:

- left: timestamped transcript quote, speaker, source, and claimed period/metric;
- right: matching filing excerpt or XBRL fact with accession and period;
- status: `supported_exactly`, `supported_approximately`,
  `different_definition`, `not_found`, or `period_mismatch`;
- separate management-guidance and GAAP-history sections; and
- user confirmation for ambiguous matches.

**Trust-boundary caveat**

Transcripts are management statements, not authoritative reported facts. The model
may extract candidate claims and suggest candidate matches, but exact company,
metric, period, and number comparisons run through deterministic resolution and
`Decimal` logic. “Not found” is not “false,” and semantic contradiction remains a
labeled model assessment.

**Novelty versus v2**

V2 has news-grounded essays and a possible filing-narrative feature, but no
transcript source or claim-to-filing reconciliation workflow.

## Idea 6 — Provenance-first segment-mix explorer

**User value**

An analyst can understand what drives a company's growth by viewing operating or
geographic segment composition over time, with every segment value tied to its
dimension, concept, period, and accession.

**Exact repo inspiration**

- Dexter's explicit financial-segments tool.
- SEC EDGAR MCP's business/geographic XBRL segment extraction.
- LangAlpha's inline financial artifacts and charts.

**Primary evidence**

- [Dexter financial segments](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/tools/finance/segments.ts)
- [SEC EDGAR MCP financial source](https://github.com/stefanoamorelli/sec-edgar-mcp/blob/88b21ad58c24ad9ab9be21e093d71571457b9057/sec_edgar_mcp/tools/financial.py)
- [LangAlpha README](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/README.md)

**UI adaptation for v2**

Add a closed `segment_mix` workflow with:

- a statement-style table as the authoritative view;
- optional stacked bars rendered only from typed values;
- operating versus geographic dimension selector;
- exact member labels and taxonomy/dimension metadata;
- reported totals beside deterministic segment sums and a reconciliation delta;
  and
- explicit `unreconciled`, `dimension_changed`, and `missing_segment` states.

**Trust-boundary caveat**

Segment taxonomies vary significantly by issuer and filing. V2 must not normalize
arbitrary members across companies without a reviewed mapping. Charts are
presentation only; underlying values remain exact strings/Decimals. A segment sum
that differs from a consolidated total is shown, never silently forced to match.

**Novelty versus v2**

The shipped metric catalog is consolidated statement facts and formulas. Segment
dimensions and segment-total reconciliation are absent from v2 and the existing
idea list.

## Idea 7 — Evidence-first bull/base/bear matrix

**User value**

An analyst can review opposing interpretations without receiving a hidden
recommendation. The view makes supporting evidence, counter-evidence, unknowns,
and disconfirming observations explicit.

**Exact repo inspiration**

- TradingAgents' bull/bear research history and structured research manager.
- twCarllin's bullish/bearish/watch evidence fields.
- AI Hedge Fund's deterministic clamp-event audit trail as a presentation model
  for “rule fired because.”

**Primary evidence**

- [TradingAgents research manager](https://github.com/TauricResearch/TradingAgents/blob/a33fd4c0f134485a43553a2c23a63cb14adbd88f/tradingagents/agents/managers/research_manager.py)
- [twCarllin three-statement skill](https://github.com/twCarllin/10k-analysis/blob/0d5e604e9d81142d8698cb42b42b7daa94053af4/skills/three_statement_cross.md)
- [AI Hedge Fund risk audit events](https://github.com/virattt/ai-hedge-fund/blob/eff8a7320fcf0b473b135690fa1a5b0d9b022a83/hedge_fund/risk/limits.py)

**UI adaptation for v2**

Add a qualitative renderer with four fixed columns:

- observation;
- evidence for a constructive interpretation;
- evidence for a cautious interpretation; and
- unknown / evidence needed.

Every row contains source chips and a fact-versus-analysis badge. The output ends
with “what would change this view,” not Buy/Hold/Sell. Deterministic guard events
can populate observations; the model may synthesize arguments from the supplied
evidence only.

**Trust-boundary caveat**

No trading action, target price, probability, or model-authored numeric fact is
allowed. The system must not pretend debate consensus is truth. All numerals must
exist in source/tool JSON, and the model-analysis banner remains visible.

**Novelty versus v2**

V2 has one qualitative essay renderer. It does not have a structured,
counter-evidence-first analysis matrix. This adapts debate without reviving the
explicitly rejected trading-agent direction.

## Idea 8 — Persistent research casebook

**User value**

An analyst can organize multiple verified turns around a company, filing, or
research question and return later without losing scope, evidence, and exported
artifacts.

**Exact repo inspiration**

- LangAlpha's workspace-per-research-goal, files, notes, and thread model.
- Filing Room's browser-local scoped history.
- Dexter's append-only scratchpad.

**Primary evidence**

- [LangAlpha workspace architecture](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/README.md)
- [Filing Room local history UI](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/web/src/pages/ResearchPage.tsx)
- [Dexter scratchpad](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/agent/scratchpad.ts)

**UI adaptation for v2**

A casebook stores:

- title and user-authored objective;
- fixed companies/CIKs and optional accessions;
- ordered immutable `TurnResult` snapshots;
- evidence records and runtime mode for each turn;
- user notes clearly separated from generated analysis;
- artifact/export links; and
- freshness badges with a “rerun using current providers” action.

The UI has a compact case list and a timeline, not an unconstrained memory prompt.

**Trust-boundary caveat**

Stored history cannot silently alter planning or become a source of current facts.
Each turn remains a closed workflow with its own evidence. Old live answers and
fixture answers are visibly labeled. Re-running creates a new immutable result
rather than mutating prior evidence.

**Novelty versus v2**

Multi-turn memory is currently out of scope, and durable workflow state is only a
generic production direction. A typed casebook of immutable turns and evidence is
a distinct product concept: persistence without model memory controlling facts.

## Idea 9 — Filing/fact threshold alert inbox

**User value**

An analyst can define a small set of precise conditions and be notified when a new
SEC filing or newly reported fact satisfies them, without asking a model to watch
the world continuously.

**Exact repo inspiration**

- EdgarTools' live SEC monitor with form filters.
- LangAlpha's automation execution history and trigger management.
- the gsaini alert center's create/active/history information architecture.

**Primary evidence**

- [EdgarTools monitor](https://github.com/dgunning/edgartools/blob/aeb15ba5562e5bdb707fa99d201d35a5f3ff600e/edgar/ai/mcp/tools/monitor.py)
- [LangAlpha execution history](https://github.com/ginlix-ai/LangAlpha/blob/d2383272b2b5a03965b82ad1ca6df986bfeb7854/web/src/pages/Automations/components/ExecutionHistoryTable.tsx)
- [Alert-center UI](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/frontend/pages/17_Alerts.py)
- [Deterministic alert engine](https://github.com/gsaini/financial-research-analyst-agent/blob/d6fe4fdb4e196005fcbd3f1158f8f28a52b9e45d/src/tools/alerts.py)

**UI adaptation for v2**

Offer closed alert templates:

- new form type for a fixed CIK;
- new standalone-quarter fact for a fixed metric;
- deterministic fact change above/below a user-entered `Decimal` threshold;
- a missing expected fact after a filing arrives; and
- an amended filing replacing a previously selected fact.

Use “Create,” “Active,” and “History” tabs. Each trigger record shows the evaluated
predicate, old/new fact provenance, evaluation time, and delivery status.

**Trust-boundary caveat**

Alerts run deterministic predicates on identified SEC records. The LLM may help
parse the initial sentence into a reviewed template, but the saved rule is typed
and user-confirmed. No model sentiment trigger, no hidden vendor price, and no
claim that absence of a fact implies a business event.

**Novelty versus v2**

This is not the existing idea to display 8-K headlines and not provider-health
monitoring. It is a user-owned, fact/provenance-aware alert product with an
evaluation ledger.

## Idea 10 — Audit-ready evidence export bundle

**User value**

An analyst can hand a result to a colleague who can reproduce where every number
and statement came from, without access to the running application.

**Exact repo inspiration**

- tenk's answer-adjacent PDF/DOCX/Excel controls.
- Filing Room's CSV export and scoped share URLs.
- Dexter's append-only tool-result records and detailed evaluation metadata.
- LangAlpha's file artifacts and export preview.

**Primary evidence**

- [tenk export UI](https://github.com/ralliesai/tenk/blob/a71a1b847efdab0c9c9165483afac7fa23b01503/src/terminal.py)
- [tenk export implementation](https://github.com/ralliesai/tenk/blob/a71a1b847efdab0c9c9165483afac7fa23b01503/src/export.py)
- [Filing Room export action](https://github.com/bcastelino/sec-filing-room/blob/de0a4ad6b51aa18372180da811cb030895a73735/apps/web/src/pages/ResearchPage.tsx)
- [Dexter scratchpad](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/agent/scratchpad.ts)
- [Dexter eval metadata](https://github.com/virattt/dexter/blob/ecaed3011f24ea24ef687ab536aa7f22f7294038/src/evals/components/eval-app.ts)

**UI adaptation for v2**

One “Export evidence bundle” action produces:

- human-readable HTML or PDF matching the structured renderer;
- CSV sheets for displayed tables;
- canonical JSON for the exact `TurnResult`;
- an evidence manifest with CIKs, accessions, periods, concepts, source URLs,
  snapshot version, news URLs, trace IDs, and runtime mode;
- formula definitions and exact component values;
- a SHA-256 digest per file; and
- application/version timestamp metadata.

**Trust-boundary caveat**

Exports are generated from typed results, never by asking the model to rewrite the
answer. Exact numeric strings must survive unchanged; compact display values are
secondary labels. Fixture exports are prominently marked. Remote source content
may disappear, so the manifest records identifiers and hashes while respecting
redistribution/licensing limits.

**Novelty versus v2**

V2 has on-screen tables and provenance but no report/export product. Existing
development ideas mention logging and observability, not a portable evidence
bundle with exact typed values and reproducibility metadata.

## Recommended order

### First: exact-source evidence inspector

This is the best near-term feature. It compounds the value of every existing
intent, requires no new financial source of truth, and makes v2's strongest
differentiator—provenance—tangible in the UI.

### Second: audit-ready evidence export bundle

The typed `TurnResult` and deterministic renderers already provide the right
foundation. Exporting that structure is lower-risk than adding a new analysis
domain and turns the portfolio project into something another analyst can review.

### Third: deterministic disclosure-change map

This adds a high-value analyst workflow while preserving a clear seam: code owns
filing/section/diff identity, and the model only summarizes supplied changes.

### Fourth: XBRL footnote lens and reconciliation checks

This deepens financial analysis, but it requires careful concept and period review.
Start with note navigation and a very small deterministic check catalog before
adding interpretive labels.

### Fifth: SEC ownership ledger

This is a clean new domain with authoritative forms and strong user value. It is
larger because owner identity, amendment chains, transaction codes, and derivative
securities need a reviewed model.

## Features to defer or reject

- **Open autonomous research/code execution:** impressive in LangAlpha and Dexter,
  but incompatible with v2's closed workflow and fact boundary.
- **LLM arithmetic or financial-model generation:** common in tenk, broad agent
  suites, and trading frameworks; conflicts directly with deterministic math.
- **Model confidence as a guardrail:** confidence is a generated field, not a
  calibrated guarantee.
- **Buy/Hold/Sell, targets, backtests, and portfolio actions:** different product
  category and explicitly outside v2's purpose.
- **Vendor values as silent replacements for SEC facts:** may be useful only as
  separately labeled context.
- **“Exact precision” inherited from third-party marketing:** implementation must
  be inspected path by path; the SEC EDGAR MCP float conversions demonstrate why.
- **Generic PDF export of generated prose:** useful-looking but loses v2's evidence
  contract unless the export is built from typed results and a manifest.

## Final assessment

Public repositories contain many more features than v2, but very few combine
closed workflows, directly reported quarterly facts, deterministic identity and
arithmetic, reproducible ranking membership, typed partial failures, and
provenance-preserving rendering.

The survey therefore supports a “deepen trust, then broaden scope” roadmap:

1. make existing evidence inspectable and portable;
2. add deterministic filing-change and footnote/reconciliation workflows;
3. expand into SEC ownership and segment facts with the same typed boundaries; and
4. borrow workspace, alert, and argument-organization UX only when it can be
   layered over closed, provenance-carrying execution.

That direction is more distinctive than copying another open agent loop and is
better aligned with the product's central promise: models interpret language and
synthesize supplied evidence; deterministic components own financial truth.
