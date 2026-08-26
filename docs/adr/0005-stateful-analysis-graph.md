# A patchable analysis spec on a persisted thread, not more closed intents

The analyst's current quantitative question is one typed **analysis spec** — resolved companies (or a snapshot-derived constituent set), closed-catalog metrics, a period selection, operations, and a requested presentation — persisted on a **conversation thread**. A turn is interpreted as a **spec patch** (add/remove/replace, `extend` or `replace` mode) that deterministic code applies, resolves, validates against the closed catalogs, and compiles into typed tasks for a workflow subgraph. The model proposes a patch; it never emits a resolved spec, never enumerates constituents, never picks a concept, never does arithmetic. Flexibility lives in the spec's dimensions (companies × metrics × periods × operations), not in model autonomy.

This supersedes "one user prompt maps to one intent" (PRD) and the one-shot rationale in ADR 0004. It does not touch ADR 0001 membership, ADR 0002 lookup/compare gating, or ADR 0003's `get_financials` seam — those run underneath, unchanged.

## Locked

- Facts stay SEC XBRL quarterly facts; formulas stay `Decimal` over period-aligned components; constituents stay snapshot-derived; identity stays CIK inside tools; essays stay numeral-locked.
- A spec must be **resolved** before any provider call. An invalid patch is a typed rejection, not a best-effort fetch.
- Metric resolution keeps running on the analyst's wording, not on a model slug (ADR 0004's phrase table).
- The parent graph's edges are fixed and typed. The model selects a workflow from a closed set; it does not select nodes or chain tools.
- Three separated state kinds: **thread state** persisted (messages, active spec, pending clarification, last result, evidence references); **run state** ephemeral (proposed patch, validation outcome, compiled tasks, task results, failures); **evidence** referenced by identifier so checkpoints stay small.
- Workflow subgraphs at introduction: structured analysis, current events, qualitative explanation, exploratory research. Each takes a resolved spec (or research request) and returns typed results — no subgraph reads conversation history.
- The exploratory lane is labelled research, read-only, cited, and cannot emit structured financial rows.
- Cross-thread memory (a long-term store), personalization, and accounts stay out.

## Seams

The new public seam is one conversation entry point: thread identifier + analyst message + runtime → typed conversation turn. `run_turn(query, runtime) → TurnResult` survives as a compatibility wrapper over an ephemeral single-message thread, so the gold suite and per-intent `run_turn` tests keep guarding XBRL selection, membership, formulas, numeral lock, and refusal catalogs for the whole migration. `Runtime` and its ports are unchanged. The presentation mapping is unchanged. Patch resolution, spec validation, and task compilation are internal seams with their own unit tests (prior art: `fact_selector`, metric phrase table); graph node names, channel names, and checkpoint payloads are not a test surface.

## Considered Options

- **More closed intents** — rejected: combinations multiply, not features. Multi-period × multi-metric × chart × explain becomes `multi_period_compare`, `compare_and_chart`, `rank_compare_and_chart`, and every planned capability (annual facts, balance-sheet ratios, peers, filing narrative, insider transactions, holdings) multiplies the routing matrix again. Spec dimensions compose for free.
- **Open ReAct over the tool set** — rejected: it trades the property that makes the agent credible. A model free to chain tools can drop a ranked constituent, pick a different XBRL concept, or rewrite a sourced number. This is the ADR-free version of design decision 1, and it stays rejected for the number path.
- **Conversation history as the state** — rejected: replaying prose to infer "what are we analysing now" is unauditable and drifts. A typed spec is inspectable, validatable, and diffable per turn.
- **Model emits a resolved spec** — rejected: resolution is where CIK identity, concept choice, and catalog membership are decided. Handing that to the model reintroduces ReAct through the schema.
- **Copy evidence into thread state** — rejected: checkpoints grow without bound and stale facts get replayed as fresh. Reference by identifier and label reuse on screen.
- **Cross-thread long-term memory** — rejected for now: preferences and personalization are a separate problem with their own privacy and staleness questions.
- **Replace `run_turn` outright** — rejected: it is the whole regression net. Wrapping keeps every step revertible and attributable.

## Consequences

Adding a metric is a catalog entry; adding a comparison is a spec operation; adding a research capability is a subgraph behind a small typed interface. None of those touch the parent graph — that is the point of the trade.

The costs are real. LangGraph becomes a dependency of the application core rather than an adapter detail. Thread persistence introduces durable local state the app must migrate and can corrupt. Two paths exist during migration (`run_turn` and the conversation seam) until the former is retired. A patch-based interface can mis-scope a follow-up — "add Apple" is unambiguous, "compare to last year" is not — so ambiguous patches must clarify rather than guess, and `extend` versus `replace` is now a decision the system can get wrong in a way one-shot turns could not.

Clarification becomes resumable: an ambiguous metric is an `interrupt` holding a pending analysis, so the analyst answers one question instead of retyping. Asking something unrelated discards the pending clarification explicitly. ADR 0004's candidate-set and phrase-table rules survive; only its "no pending plan" mechanism does not.
