# Interview playbook

Use this as a speaking guide, not a script to read verbatim. The goal is to show judgment:
the system is agentic where interpretation helps and deterministic where correctness matters.

## One-sentence pitch

This is a financial-analysis agent that routes natural-language questions through a closed set
of intents, uses deterministic tools for financial data and calculations, and shows the source
and execution trace for every answer.

## The 25-minute walkthrough

### 0:00–2:00 — Frame the problem

> Financial questions mix interpretation with high-stakes numbers. I wanted the model to
> understand the request, but I did not want it selecting facts, doing arithmetic, choosing
> ranking members, or rewriting sourced values.

State the three requirements:

1. Retrieve directly reported quarterly facts with filing provenance.
2. Rank a reproducible set of public operating companies.
3. Compose tools from one prompt without letting the model invent intermediate data.

Then give the design thesis:

> The model chooses from six typed intents. The executor owns tool composition. Structured
> answers are rendered from typed tool output rather than generated prose.

### 2:00–6:00 — Walk the architecture

Open [`../design.md`](../design.md) and use its diagram.

Follow one request from left to right:

1. `run_turn(query, runtime)` is the single application seam.
2. The metric phrase gate catches ambiguous or unsupported metrics before tools run.
3. The structured planner selects a closed intent and extracts names.
4. The executor calls the appropriate adapter or fixed tool composition.
5. A typed `TurnResult` selects a table, essay, refusal, or clarification renderer.

Call out the key boundary:

> Identity resolution is inside the tools. For a rank-and-lookup request, the executor carries
> CIKs from ranking output into fact lookup. The model never generates the constituent list.

Mention that Streamlit, fixture mode, and tests all use the same `run_turn` seam. FastMCP exposes
the same five capabilities as an HTTP service boundary; it is not a separate implementation.

### 6:00–8:00 — Explain the reliability locks

Focus on four:

- **SEC XBRL is primary.** A quarterly fact is a directly reported standalone 10-Q duration,
  with accession, concept, period, and EDGAR URL.
- **No model arithmetic.** Ratios use `Decimal` and period-aligned named components.
- **Ranking is reproducible.** Membership comes from a dated snapshot, with non-operating
  listings and duplicate share classes excluded.
- **Failure is visible.** Ambiguous input clarifies, unsupported input refuses, and a missing
  constituent fact produces a partial row instead of fabricated data.

Transition:

> Rather than show more boxes, I’ll run three prompts that each exercise a different guarantee.

### 8:00–18:00 — Run the three demos

Before the first prompt, point to the **Live** badge. If fixture mode is enabled, say:

> I’m switching to the recorded fixture runtime because a live dependency is unavailable. It
> uses the same executor and renderer, but these are recorded facts rather than live EDGAR.

#### Demo 1 — Direct quarterly lookup

Prompt:

> What was Microsoft's latest quarterly pre-tax income?

Narrate:

- The planner chose `lookup`.
- The metric phrase resolved to the closed `pretax_income` catalog entry.
- The result is a directly reported 10-Q fact, not TTM and not a derived quarter.
- Open the trace or filing link and point out the period, accession, taxonomy, and concept.

Do not memorize or predict the value. Read it from the result.

Transition:

> That proves a single sourced fact. Next I’ll show deterministic comparison across issuers.

#### Demo 2 — Period-aware comparison

Prompt:

> Compare TSLA and GM quarterly revenue.

Narrate:

- The planner chose `compare`; one deterministic tool owns both issuers.
- Each row resolves the company to a CIK and selects its reported quarterly revenue.
- The table makes periods visible. For formulas, components must share the same start and end.
- A missing or incompatible fact is reported as a typed row-level reason.

Transition:

> The more important composition case is ranking first and then looking up a filing fact for
> every ranked company.

#### Demo 3 — Rank and lookup

Prompt:

> What are the top 10 technology companies and R&D spend for each?

Narrate:

- The planner chose `rank_and_lookup`.
- Ranking reads the dated market-cap snapshot and returns CIKs.
- The executor passes those CIKs into SEC fact lookup; the model does not type tickers.
- Share classes collapse to one company, and missing R&D produces a partial row.
- The snapshot timestamp and filing provenance expose the two different data sources.

Pause on the tool traces. This is the strongest proof of multi-tool composition.

### 18:00–21:00 — Show honest boundaries

Use one or two quick prompts:

- `income` → clarification with colliding metric names and no tool call.
- `What are the top 10 companies in AI?` → refusal because AI is not a closed industry.
- `What is Apple's market cap?` → snapshot value, clearly distinct from a quarterly filing fact.

Say:

> These are product behaviors, not error messages I hope users never see. The system preserves
> trust by making uncertainty and unsupported scope explicit.

### 21:00–25:00 — Close with production judgment

What is already designed for change:

- Adapters are injected through `Runtime`, so live and fixture implementations are replaceable.
- The application contract is `run_turn`; UI and tests do not depend on provider details.
- Typed models keep provenance attached through execution and presentation.

What you would add next:

1. Persist snapshots and filing responses in an observable data pipeline with freshness SLAs.
2. Add authentication, authorization, rate limiting, caching, retries, and provider monitoring.
3. Add evaluation sets for routing, entity resolution, fact selection, and refusal quality.
4. Add PDF verification as a warning-bearing fallback, not an equal source of truth.
5. Expand the metric catalog deliberately, including ambiguity tests for every new alias.

Close:

> The central trade-off is constrained agency. I use the model for language understanding and
> qualitative synthesis, while deterministic code owns membership, financial facts, arithmetic,
> and rendering. That is what makes the demo inspectable and gives it a credible production path.

## Optional news demo

Only run the news prompt if Tavily was refreshed and rehearsed the same day:

> Effects of recent Strait of Hormuz closures on Exxon

Explain that the executor searches the full user query, drops unusable hits, and grounds the
essay only in returned hit JSON. Empty search results refuse. The numeral lock rejects numeric
tokens that were not present in tool output.

## Recovery phrases

- **Live SEC failure:** “I’ll switch to the labeled fixture runtime. The application path is
  unchanged; only the adapter is recorded.”
- **Unexpected missing fact:** “This is the intended partial-result behavior. The selector will
  not derive a quarter or silently choose a different concept.”
- **Planner surprise:** “The intent and extracted parameters are visible, so the routing error
  is inspectable. In production I would add this prompt to the routing evaluation set.”
- **Slow network:** “The external provider is on the critical path in this POC. Production would
  add caching, timeouts, retries, and a freshness policy.”
- **Asked for unsupported scope:** “That is outside the closed catalog today. I prefer an
  explicit refusal to a plausible but semantically wrong number.”
