# Technical interview Q&A

Answer with the first paragraph, then add the bullets only if the interviewer wants depth.

## Architecture and agent design

### Why use closed intents instead of a ReAct loop?

The task has a small number of high-value workflows and strict correctness requirements. A closed
intent gives the model enough freedom to interpret language while keeping execution testable and
bounded. Tool composition lives in code, so the model cannot omit a ranked constituent, invent an
identifier, or choose an unapproved source.

- The six intents are `lookup`, `compare`, `rank`, `rank_and_lookup`, `explain`, and
  `news_and_explain`.
- A new workflow requires an explicit contract and tests rather than an accidental prompt path.
- Open-ended planning could be appropriate later for low-risk exploration, but not for the
  source-of-truth path for financial numbers.

### Is this really an agent?

Yes, but it is deliberately constrained. The model interprets the question, selects a typed
workflow, extracts entities, and produces qualitative synthesis where appropriate. Deterministic
executors and tools control high-risk operations. Agency is a spectrum; unconstrained tool
chaining is not a requirement.

### Why is `run_turn` the main interface?

It creates one stable application seam for Streamlit, tests, and fixture mode. Provider clients,
MCP transport, and presentation can change without creating different product behaviors.

- `Runtime` injects facts, ranking, news, and model adapters.
- `TurnResult` carries intent, traces, renderer choice, data, banners, and failures.
- Tests assert observable behavior at this seam rather than UI widgets or provider HTTP details.

### Why MCP if the app calls tools in-process?

MCP demonstrates a real service boundary without making the live demo depend on a fragile local
subprocess. FastMCP exposes the same five tool capabilities over HTTP, while the application can
call the implementations in-process. The contract is real; the transport is optional.

### Where would LangGraph or another graph framework add value?

The typed workflow already behaves as a small graph: validate, plan, execute, and render. A graph
framework becomes more valuable when the product needs durable checkpoints, human approvals,
parallel branches, retries with state, or long-running workflows. Adding it only for visual
complexity would increase failure modes without improving this POC.

## Financial-data correctness

### Why SEC companyfacts XBRL instead of parsing the 10-Q document?

Companyfacts provides structured values with concepts, units, periods, forms, and accession
numbers. That makes selection deterministic and provenance explicit. PDF or HTML parsing is
useful as a later verification fallback, but making it primary would introduce layout and table
interpretation errors into the core path.

### How do you define “latest quarterly”?

It is a directly reported standalone-quarter duration from a 10-Q, roughly 70–110 days, with the
expected unit and filing metadata. The selector does not subtract year-to-date values or derive
Q4. If no valid standalone fact exists, the system refuses instead of manufacturing one.

### How do you handle multiple XBRL concepts for the same metric?

The metric catalog defines ordered acceptable concepts. Selection applies form, period, unit,
accession, and duration constraints. If the remaining candidates are genuinely ambiguous, the
system raises a typed ambiguity rather than choosing silently. The trace exposes the selected
taxonomy and concept.

### Why `Decimal` instead of `float`?

Financial amounts and ratios should not acquire binary floating-point artifacts. Values remain
decimal through selection, deterministic formulas, serialization, and presentation.

### How are ratios computed?

Each formula maps to two named catalog components, such as operating income divided by revenue.
The executor fetches both components, requires aligned start and end dates, checks a zero
denominator, and divides with `Decimal`. The model performs no arithmetic.

### How do you prevent stale or incomparable data?

The UI exposes periods and snapshot timestamps instead of hiding freshness. Filing facts come
from the selected filing; ranking comes from a dated freeze. Formula components must align.
Production would add explicit freshness SLAs, scheduled snapshot builds, and monitoring.

## Ranking and identity

### Why use a dated snapshot instead of a live screener?

A freeze makes membership and ordering reproducible during the interview and in tests. A live
screener can change between prompts or fail mid-demo. The timestamp is visible, and the system
does not claim global or complete market coverage.

### What belongs in the ranking set?

US exchange-listed common shares of operating companies in the snapshot. Funds, ETFs, SPACs,
BDCs, shells, notes, preferreds, and similar non-operating listings are excluded structurally.
Residual false positives are recorded by CIK, so future data refreshes do not reintroduce them.

### How do you avoid counting GOOG and GOOGL twice?

Identity resolves to CIK, and ranking consolidates share classes at the issuer level. Tickers are
presentation identifiers; CIK is the stable key passed between ranking and fact lookup.

### Why is identity resolution inside tools?

It keeps the planner from coordinating names, tickers, and CIKs across separate steps. Each tool
accepts a user-facing identifier and returns canonical identity with its result. Rank-and-lookup
passes the ranking CIK directly, avoiding a second lossy resolution.

### What happens to a company absent from the ranking snapshot?

A quarterly lookup may still succeed because filing eligibility and snapshot membership are
different concepts. Market-cap lookup requires snapshot presence because that metric is sourced
from the freeze. A known ineligible non-operating issuer is rejected regardless of freeze
presence.

## Safety, grounding, and failures

### How do you stop hallucinated numbers?

Structured responses are rendered directly from typed tool fields, not rewritten by the model.
For essays, a numeral lock compares numeric tokens in generated text with tokens present in tool
JSON. An unsupported token causes refusal rather than display.

### What is the difference between clarification and refusal?

Clarification means the phrase matches multiple supported metrics, such as “income” or “margin.”
The app lists only the colliding names and calls no tools. Refusal means the request names no
supported metric or industry, so the app shows the closed allowed set.

### Why allow partial results?

Discarding nine valid rows because one issuer lacks a fact is less useful and can hide the real
data-quality issue. Each row carries either a value and provenance or a typed reason such as a
missing fact, ambiguity, period mismatch, or zero denominator.

### How is news grounded?

The news adapter searches the full question with a constrained Tavily wrapper, keeps at most five
usable hits, and requires titles and URLs. The essay is generated from those hits only and shows
citations. Empty usable results refuse rather than falling back to model memory.

### What does fixture mode prove?

Fixture mode proves deterministic application behavior under recorded adapters, not live
provider freshness. It uses the same `run_turn` and renderer as live mode. The UI labels it
prominently, and it must be announced aloud.

## Testing and production

### What is your testing strategy?

Most tests are offline and assert `run_turn` outcomes: intent, tool traces, values, provenance,
renderer, refusal behavior, and partial rows. Focused provider tests cover SEC selection and HTTP
adapters. Gold tests replay the interview prompts through fixture mode; network-marked tests
rehearse live integrations separately.

### What would you monitor in production?

- Routing accuracy and clarification/refusal rates
- Provider latency, timeout, error, and rate-limit rates
- Fact-selection ambiguity and missing-fact rates by metric and issuer
- Snapshot age and build failures
- Citation coverage and numeral-lock rejection rates
- End-to-end latency by intent and tool
- User corrections, reopened sources, and unsupported-query demand

### How would you scale it?

Separate stateless request execution from scheduled data ingestion. Cache SEC responses by CIK
and accession, store versioned ranking snapshots, queue expensive refreshes, and apply provider
rate limits centrally. Keep typed tool contracts stable so workers and transports can evolve
without changing product semantics.

### What are the largest current risks?

1. Provider availability and rate limits on a synchronous demo path.
2. XBRL taxonomy variation as the metric and issuer catalog grows.
3. Entity-resolution edge cases involving successors and unusual listings.
4. Snapshot freshness and vendor classification quality.
5. Routing quality outside the rehearsed prompt distribution.

The mitigation is not “use a smarter model” alone. It is provider observability, versioned data,
evaluation sets, explicit contracts, and human-review paths.

### What did you intentionally leave out?

Authentication, deployment, durable state, broad document parsing, balance-sheet ratios,
unconstrained web browsing, and open-ended tool planning. The POC prioritizes a correct,
inspectable vertical slice over shallow breadth.

### What would you change with another week?

First, productionize the data path: caching, scheduled snapshots, provider telemetry, and a
larger captured-fixture corpus. Second, build routing and fact-selection evaluations from real
questions. Third, add PDF verification with explicit disagreement handling. Only then expand the
metric and workflow catalog.

## Questions to ask the interviewer

- Which analyst workflows create the highest cost when a number is wrong versus merely missing?
- How do you evaluate grounding and provenance in your current agent systems?
- Where do you draw the boundary between model planning and deterministic orchestration?
- Are financial-data providers treated as online dependencies or ingested into an internal
  versioned store?
- What production constraints matter most here: latency, freshness, coverage, or auditability?
