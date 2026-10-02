# A patchable analysis spec on a persisted thread, not more closed intents

The analyst's current quantitative question is one typed **analysis spec** — resolved companies (or a snapshot-derived constituent set), closed-catalog metrics, a period selection, operations, and a requested presentation — persisted on a **conversation thread**. A turn is interpreted as a **spec patch** (add/remove/replace, `extend` or `replace` mode) that deterministic code applies, resolves, validates against the closed catalogs, and compiles into typed tasks for a workflow subgraph. The model proposes a patch; it never emits a resolved spec, never enumerates constituents, never picks a concept, never does arithmetic. Flexibility lives in the spec's dimensions (companies × metrics × periods × operations), not in model autonomy.

This supersedes "one user prompt maps to one intent" (PRD) and the one-shot rationale in ADR 0004. It does not touch ADR 0001 membership, ADR 0002 lookup/compare gating, or ADR 0003's `get_financials` seam — those run underneath, unchanged.

## Locked

- Facts stay SEC XBRL quarterly facts; formulas stay `Decimal` over period-aligned components; constituents stay snapshot-derived; identity stays CIK inside tools; essays stay numeral-locked.
- A spec must be **resolved** before any provider call. An invalid patch is a typed rejection, not a best-effort fetch.
  - *Revised:* a period window or named period on a **ranked list** is a valid spec whose rows show each member's latest quarter, because constituents are snapshot-dated and fiscal calendars differ across members. The answer says so in a banner ("Ranked lists show each company's latest quarter. Name the companies to see a multi-quarter window.") rather than refusing; naming the companies runs the full window.
- Metric resolution keeps running on the analyst's wording, not on a model slug (ADR 0004's phrase table).
- The parent graph's edges are fixed and typed. The model selects a workflow from a closed set; it does not select nodes or chain tools.
- Three separated state kinds: **thread state** persisted (messages, active spec, pending clarification, last result, evidence references); **run state** ephemeral (proposed patch, validation outcome, compiled tasks, task results, failures); **evidence** referenced by identifier so checkpoints stay small. Run state is the graph's channels; it is checkpointed only while the graph is paused on a clarification, and that checkpoint is the thread's pending clarification. Thread state reaches the graph as per-turn context, never as a channel.
- Workflows: structured analysis is a subgraph (run tasks → merge → add history → annotate); current events, qualitative explanation, exploratory research, and filing comparison are single nodes, each one provider call held to the numeral lock, so a subgraph boundary around them would hold nothing. Each takes a typed request (a compiled analysis, a topic, or the analyst's question) and returns typed results — none reads conversation history.
- The exploratory lane is labelled research, read-only, cited, and cannot emit structured financial rows.
- Cross-thread memory (a long-term store), personalization, and accounts stay out.

## Seams

The new public seam is one conversation entry point: thread identifier + analyst message + runtime → typed conversation turn. `run_turn(query, runtime) → TurnResult` survives as a compatibility wrapper over an ephemeral single-message thread, so the gold suite and per-intent `run_turn` tests keep guarding XBRL selection, membership, formulas, numeral lock, and refusal catalogs for the whole migration. `Runtime` and its ports are unchanged. The presentation mapping is unchanged. Patch resolution, spec validation, and task compilation are internal seams with their own unit tests (prior art: `fact_selector`, metric phrase table). The graph's nodes and edges are pinned by one structural test, because the shape is the design; channel names and checkpoint payloads are not a test surface.

## Graph

`graph/turn_graph.py` runs one turn as fixed, typed steps over `AnalysisRun` (message, typed request, held clarification, applied patch, compiled analysis, result, the analysis answered and the one the thread keeps):

- `interpret` — the only step that calls the model. A guide reply ends the turn; otherwise the planner's proposal is typed as one closed request: `StructuredRequest` (a spec patch plus the analyst's wording), `QualitativeRequest`, or `FilingChangeRequest`. Anything else is an error, not a fallback.
- `resolve` — patch → resolve → validate → materialize periods → compile, with no fetch. It refuses, asks one question (ambiguous metric, or ambiguous extend/replace), or emits a `CompiledAnalysis`.
- `clarify` — calls `interrupt(Clarification)`. The analyst's next message resumes it with `Command(resume=message)`; deterministic code decides whether the message answers the held question (→ `resolve` with the choice filled in), keeps it open (a period for it, or an option out of range → `clarify` again), or asks something new (→ `interpret`, the held analysis discarded explicitly and the answer says so).
- `structured_analysis` — the subgraph: `run_tasks` (bounded, deadline-aware provider fan-out), `merge` (period-aligned rows, `Decimal` changes), `add_history` (overview trend, prior quarter), `annotate` (notes, the resolved spec the thread keeps).
- `explain`, `current_events`, `exploratory_research`, `filing_change` — one node each.

Edges are fixed; three conditional edges (`interpret`, `resolve`, `clarify`) route on typed state through explicit path maps. Providers, the active spec, and the last answer's rows reach nodes as LangGraph context (`TurnDeps`), not state.

**Checkpointer.** `ThreadCheckpointer` is a `BaseCheckpointSaver` that keeps one thread's latest checkpoint and its pending writes (the interrupt), and the conversation seam stores it in the thread record (`ThreadState.checkpoint`). Turns run with `durability="exit"`, so a paused turn writes one checkpoint and a finished turn keeps none: a record carries a checkpoint only while a clarification is open, and the next turn, in this process or after a restart, restores it and resumes. Keeping it in the record rather than a separate store means one atomic write (temp file and `os.replace`) commits the thread and its paused run together; Start over and expiry remove both; a turn the API abandoned writes neither. Deserialization is limited to the graph's own models. A checkpoint that cannot be read back is dropped and the turn starts fresh, rather than failing every later turn. Records saved before this mechanism kept the open question as `pending_clarification`; the next turn carries it into the graph (`update_state` as though `resolve` had just asked it), so the answer still resumes it.

## Considered Options

- **More closed intents** — rejected: combinations multiply, not features. Multi-period × multi-metric × chart × explain becomes `multi_period_compare`, `compare_and_chart`, `rank_compare_and_chart`, and every planned capability (annual facts, balance-sheet ratios, peers, filing narrative, insider transactions, holdings) multiplies the routing matrix again. Spec dimensions compose for free.
- **Open ReAct over the tool set** — rejected: it trades the property that makes the agent credible. A model free to chain tools can drop a ranked constituent, pick a different XBRL concept, or rewrite a sourced number. This is the ADR-free version of design decision 1, and it stays rejected for the number path.
- **Conversation history as the state** — rejected: replaying prose to infer "what are we analysing now" is unauditable and drifts. A typed spec is inspectable, validatable, and diffable per turn.
- **Model emits a resolved spec** — rejected: resolution is where CIK identity, concept choice, and catalog membership are decided. Handing that to the model reintroduces ReAct through the schema.
- **Copy evidence into thread state** — rejected: checkpoints grow without bound and stale facts get replayed as fresh. Reference by identifier and label reuse on screen.
- **Cross-thread long-term memory** — rejected for now: preferences and personalization are a separate problem with their own privacy and staleness questions.
- **Replace `run_turn` outright** — rejected: it is the whole regression net. Wrapping keeps every step revertible and attributable.
- **A SQLite checkpointer (`langgraph-checkpoint-sqlite`) or another separate checkpoint store** — rejected for one process with a file-backed thread store: a second store must be kept consistent with the thread record (a crash between the two writes, Start over, expiry, abandoned turns) and adds a dependency, and the app gains nothing from it. Swapping the thread store for a server-backed one would move both together.
- **Keep every checkpoint (time travel)** — rejected: nothing replays or forks a turn, and the history would grow the record with every step.
- **Hold the pending clarification as a hand-written record beside the graph** — superseded: the held question, its patch, and the answer-reading step now live in the graph, so resuming is LangGraph's `interrupt` and `Command(resume=...)` rather than a parallel code path.

## Consequences

Adding a metric is a catalog entry; adding a comparison is a spec operation; adding a research capability is a subgraph behind a small typed interface. None of those touch the parent graph — that is the point of the trade.

The costs are real. LangGraph becomes a dependency of the application core rather than an adapter detail. Thread persistence introduces durable local state the app must migrate and can corrupt; the paused graph run shares the thread record's atomic write, and an unreadable checkpoint is dropped rather than trusted. A resumed node runs again from its start, so `clarify` reads only its held question and the resume value, and asking again is a fresh pass through `clarify` rather than a loop that would replay earlier answers. Two paths exist during migration (`run_turn` and the conversation seam) until the former is retired. A patch-based interface can mis-scope a follow-up — "add Apple" is unambiguous, "compare to last year" is not — so ambiguous patches must clarify rather than guess, and `extend` versus `replace` is now a decision the system can get wrong in a way one-shot turns could not.

Clarification becomes resumable: an ambiguous metric is an `interrupt` holding a pending analysis, checkpointed in the thread record and resumed with `Command(resume=...)` keyed by the thread id, so the analyst answers one question instead of retyping. Asking something unrelated discards the pending clarification explicitly: `clarify` routes the message back to `interpret` and the answer carries a set-aside note. ADR 0004's candidate-set and phrase-table rules survive; only its "no pending plan" mechanism does not.
