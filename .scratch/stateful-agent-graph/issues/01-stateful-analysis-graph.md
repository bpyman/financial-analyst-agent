# 01 — Stateful analysis graph

**Status:** ready-for-agent

## Problem Statement

Today every question is a fresh one-shot turn. `run_turn` plans one closed intent, runs a fixed workflow, and returns a `TurnResult` that is thrown away. Nothing carries forward.

That costs the analyst three things:

1. **No follow-ups.** "Now add R&D intensity", "use Apple instead of Google", "show the last four quarters" all require retyping the whole question. The agent cannot see what was just computed.
2. **No composition.** One prompt maps to one intent, so a question that mixes several metrics, several companies, and several periods either collapses into the nearest single intent or refuses. Combining "compare these two companies on revenue and operating margin across four quarters" is not expressible.
3. **No resumable clarification.** An ambiguous metric returns a clarify pane and discards the planned work; the analyst retypes the whole question instead of answering the one open question.

It also costs Blake future velocity. Every new analyst capability currently arrives as a new intent, and combinations multiply: `multi_period_compare`, `multi_metric_compare`, `compare_and_chart`, `rank_compare_and_chart`, `compare_then_explain`. The routing matrix grows faster than the feature set. The planned additions (annual facts, balance-sheet ratios, peers, filing narrative, insider transactions, institutional holdings, scheduled recipes) would each multiply that matrix again.

The naive fix — an open ReAct loop over the tool set — trades the exact property that makes this agent credible. Deterministic code owns facts, identity, arithmetic, snapshot membership, and rendering; a model that picks tools and chains them freely can drop a ranked constituent, pick a different XBRL concept, or rewrite a sourced number.

## Solution

Redesign the application around a **stateful analysis graph**: a persisted conversation thread whose durable centre is a typed, patchable **analysis spec**, executed by deterministic workflow subgraphs.

The analyst asks a question. The model interprets that turn as a **spec patch** — add a company, drop a metric, change the period window, add a comparison — and deterministic code resolves the patch against the thread's current spec, validates it against the closed catalogs, compiles it into typed tasks, dispatches those tasks to the appropriate workflow, and renders the result. The spec, the evidence, and the last result persist on the thread, so the next turn edits an analysis instead of restarting one.

Flexibility comes from the spec being compositional (any supported companies × metrics × periods × operations), not from giving the model tool authority. The model proposes; typed code disposes. Facts still come from SEC XBRL, arithmetic still uses `Decimal`, ranked constituents still come from the universe snapshot, essays still pass the numeral lock, and unsupported scope still refuses with the closed allowed set.

A small parent graph owns conversation and coordination. Financial behaviour lives in workflow subgraphs behind small typed interfaces, so a new capability is a new subgraph or a new spec operation rather than an edit to a central router. Clarification becomes an `interrupt` on the thread: the analyst answers the one open question and the pending analysis resumes.

Migration is incremental. `run_turn(query, runtime)` survives as a compatibility wrapper over a single ephemeral thread, so the existing gold suite stays green while the stateful interface grows beside it.

## User Stories

### Multi-turn analysis

1. As an analyst, I want to ask a follow-up that edits my previous question, so that I do not retype the whole thing.
2. As an analyst, I want to add a metric to the analysis I just ran, so that I can widen a comparison one step at a time.
3. As an analyst, I want to remove a metric from the current analysis, so that I can narrow a table that got too wide.
4. As an analyst, I want to add a company to the current analysis, so that I can bring a peer into a comparison I already trust.
5. As an analyst, I want to swap one company for another, so that "use Apple instead of Google" keeps the rest of my analysis intact.
6. As an analyst, I want to change the period window, so that "make that the last four quarters" re-runs the same metrics over more periods.
7. As an analyst, I want to add a comparison to the current analysis, so that "show year over year" applies to what is already on screen.
8. As an analyst, I want to ask a fresh unrelated question in the same thread, so that starting over does not require a new session.
9. As an analyst, I want to see which companies, metrics, periods, and comparisons are currently active, so that I know what the next follow-up will edit.
10. As an analyst, I want the active analysis to survive a browser refresh, so that a reload does not lose my work.
11. As an analyst, I want to revisit an earlier thread, so that yesterday's analysis is still there.
12. As an analyst, I want each thread to carry its own analysis and evidence, so that two investigations do not bleed into each other.

### Composition

13. As an analyst, I want one question to cover several companies and several metrics at once, so that a realistic analyst question does not have to be split.
14. As an analyst, I want one question to cover several periods, so that a trend is a single request.
15. As an analyst, I want to compare across companies for a given period, so that a cross-sectional question is directly expressible.
16. As an analyst, I want to compare across periods for a given company, so that sequential and year-over-year change are directly expressible.
17. As an analyst, I want a ranked set to feed the same metric machinery as named companies, so that "top 10 technology companies and R&D spend for each" is the same composition as a two-company compare.
18. As an analyst, I want partial results when one cell of a wide analysis is missing, so that one absent quarterly fact does not sink the table.
19. As an analyst, I want each missing cell to state its typed reason, so that I can tell a missing fact from a period mismatch from an ambiguous concept.
20. As an analyst, I want an unsupported combination refused explicitly, so that the agent does not silently compute something adjacent to what I asked.

### Resumable clarification

21. As an analyst, I want an ambiguous metric to ask me one question, so that I answer the ambiguity rather than retyping the request.
22. As an analyst, I want my answer to that question to resume the pending analysis, so that the work planned before the clarification is not discarded.
23. As an analyst, I want the clarify options to remain the colliding catalog names only, so that the closed catalog still owns the candidate set.
24. As an analyst, I want no tools to run while a clarification is pending, so that an ambiguous question never touches a provider.
25. As an analyst, I want to abandon a pending clarification by asking something else, so that I am not trapped in a question I no longer care about.
26. As an analyst, I want an unknown metric to still refuse with the full allowed list, so that clarification and refusal stay distinct product states.

### Trust boundary

27. As an analyst, I want quarterly numbers to keep coming from directly reported SEC XBRL facts, so that the flexibility does not cost me provenance.
28. As an analyst, I want ratios to keep being computed by deterministic formulas over period-aligned components, so that no model does arithmetic.
29. As an analyst, I want ranked constituents to keep coming from the dated universe snapshot, so that the model cannot type a company list.
30. As an analyst, I want company identity to keep resolving to CIK inside tools, so that a share class cannot double-count and a ticker cannot be invented.
31. As an analyst, I want every displayed value to keep its filing or snapshot provenance, so that I can verify any number in the analysis.
32. As an analyst, I want essays to keep passing the numeral lock, so that qualitative synthesis cannot introduce a number that no tool returned.
33. As an analyst, I want the model to be unable to substitute an unapproved source, so that "latest quarterly" never silently becomes a vendor figure.
34. As Blake, I want the spec validated against the closed catalogs before any provider call, so that a bad patch fails cheaply and legibly.
35. As Blake, I want the model's proposal recorded separately from the resolved spec, so that I can show what the model asked for and what the system allowed.

### Exploratory lane

36. As an analyst, I want a question that does not fit structured analysis to be handled by a clearly labelled exploratory path, so that unusual requests are still useful.
37. As an analyst, I want exploratory answers visibly marked as research rather than reported facts, so that I never confuse the two.
38. As an analyst, I want the exploratory path restricted to read-only approved capabilities, so that flexibility does not become unbounded web browsing.
39. As an analyst, I want exploratory output to cite its evidence, so that a research draft can be checked.
40. As Blake, I want the exploratory path unable to write structured financial facts, so that the reliable table path stays reliable.

### Evidence and artifacts

41. As an analyst, I want the evidence behind the current analysis retained on the thread, so that a follow-up can reuse it instead of refetching.
42. As an analyst, I want to see when a value came from cached thread evidence rather than a fresh fetch, so that freshness is never implied.
43. As an analyst, I want a later qualitative question to receive the deterministic result already computed, so that an explanation is grounded in the same numbers I am looking at.
44. As Blake, I want evidence referenced by identifier rather than copied into every checkpoint, so that thread state stays small.

### Operability

45. As Blake, I want the thread state persisted locally, so that the app survives a restart without a database server.
46. As Blake, I want a thread identifier owned by the application, so that hosting the app later does not require redesigning state.
47. As Blake, I want long-running analyses to stream progress, so that a wide multi-period request does not look hung.
48. As Blake, I want independent tasks in one analysis executed concurrently, so that eight quarters times four metrics is not eight times four sequential round trips.
49. As Blake, I want a failed provider call to fail that task and not the thread, so that one bad cell does not destroy the conversation.
50. As Blake, I want the fixture kill-switch to keep swapping adapters only, so that recorded and live runs share one graph topology.
51. As Blake, I want the graph's node and transition set to stay inspectable, so that the demo can show a real typed workflow rather than a hidden loop.

### Extensibility

52. As Blake, I want a new metric to be a catalog entry rather than a graph change, so that widening coverage is cheap.
53. As Blake, I want a new comparison to be a new spec operation rather than a new intent, so that combinations do not multiply routes.
54. As Blake, I want a new research capability to be a new subgraph behind a small typed interface, so that adding filing narrative, insider transactions, or institutional holdings does not touch the structured analysis path.
55. As Blake, I want a new renderer to consume typed results rather than reach into graph state, so that presentation and execution evolve independently.
56. As Blake, I want the MCP tool contracts preserved, so that the service boundary stays real as the orchestration changes.

### Migration

57. As a developer, I want the existing `run_turn` contract preserved during migration, so that the gold suite keeps guarding XBRL selection, membership, and refusal behaviour throughout.
58. As a developer, I want the stateful interface added beside `run_turn` rather than replacing it in one step, so that no commit leaves the app broken.
59. As a developer, I want the existing runtime ports reused unchanged, so that adapters, fixtures, and recorded evidence keep working.
60. As a developer, I want the deterministic tool implementations reused rather than rewritten, so that ported v1 fact-selection invariants survive.
61. As a developer, I want each migration step independently verifiable, so that a regression is attributable to one change.
62. As a developer, I want the one-shot clarify decision explicitly revised rather than quietly contradicted, so that the written trail matches the code.

## Implementation Decisions

### Seams

- **Primary new seam:** one conversation entry point taking a thread identifier, an analyst message, and a runtime, returning a typed conversation turn. This replaces `run_turn` as the highest seam and is where new behaviour is asserted. It is the only new public seam this spec introduces.
- **Existing seam kept:** `run_turn(query, runtime) -> TurnResult` becomes a thin compatibility wrapper that opens an ephemeral single-message thread and returns the same `TurnResult` shape. It stays the gold-test surface unchanged for the whole migration.
- **Existing seam kept:** the `Runtime` dataclass and its ports (`Completer`, `FactsPort`, `RankingPort`, `NewsPort`, `EssayCompleter`) are unchanged. Live and fixture wiring is untouched.
- **Existing seam kept:** the presentation mapping from a result to display records. The stateful turn adds fields; it does not move formatting into the graph or into Streamlit.
- **Internal seams (implementation detail, not public):** spec patch resolution, spec validation, and task compilation are pure functions inside the graph package. They get their own unit tests following existing prior art for the metric phrase table and the fact selector, but callers outside the graph package do not depend on them.
- No new seam for graph internals. Node names, edge lists, checkpoint payloads, and channel names are not a test surface.

### Analysis spec

- The thread's quantitative state is one **analysis spec**: the companies, metrics, period selection, operations, and requested presentation that define the current question.
- A spec is **resolved** — companies carry CIKs, metrics carry catalog slugs, periods carry concrete bounds — before any provider call. An unresolved spec cannot execute.
- The model never emits a resolved spec. It emits a **spec patch**: a proposal of additions, removals, and replacements, plus whether this turn continues or replaces the current analysis. Deterministic code applies the patch, resolves identity and metrics, and validates the result.
- Decision shape from grilling, trimmed to the decision-rich parts:

```python
class AnalysisSpec:
    companies: tuple[ResolvedCompany, ...]      # CIK-keyed, share classes collapsed
    constituents: RankedSet | None               # snapshot-derived, model cannot type this
    metrics: tuple[MetricSlug, ...]              # closed catalog only
    periods: PeriodSelection                     # latest standalone quarter | last N quarters | named annual
    operations: tuple[Operation, ...]            # across-companies | across-periods | ratio | rank
    presentation: PresentationRequest            # table | table+chart

class SpecPatch:                                 # what the model may propose
    mode: Literal["extend", "replace"]
    add_companies / remove_companies
    add_metrics / remove_metrics
    set_periods
    add_operations / remove_operations
    set_presentation
```

- Metric resolution keeps running on the analyst's own wording, not on the model's slug. An ambiguous metric phrase in a patch produces a clarification, not a guess.
- Adding a metric to the catalog, or an operation to the operation set, must not require touching the parent graph.

### Graph and state

- LangGraph is added as a dependency. The parent graph owns interpreting the turn, resolving and validating the spec, dispatching to a workflow subgraph, and assembling the turn result. Edges out of the parent graph are fixed and typed; the model selects a workflow from a closed set, it does not choose nodes.
- Workflow subgraphs at introduction: **structured analysis** (facts, formulas, ranking, multi-period), **current events** (bounded news plus grounded essay), **qualitative explanation** (model analysis with the model-analysis banner), and **exploratory research** (labelled, read-only, cannot write structured facts). Filing narrative, insider transactions, and institutional holdings are later subgraphs, out of scope here.
- Each subgraph presents a small typed interface: resolved spec or research request in, typed results and evidence references out. Subgraphs do not read the parent's conversation history.
- Three kinds of state, kept separate:
  - **Thread state (persisted):** messages, active analysis spec, pending clarification, last completed result, evidence references, and analyst-visible decisions.
  - **Run state (ephemeral):** proposed patch, validation outcome, compiled tasks, task results, failures, and rendering instructions. Not carried between turns.
  - **Evidence store (referenced):** fetched facts, news hits, and artifacts, addressed by identifier so checkpoints stay small.
- Persistence uses a durable local checkpointer keyed by thread identifier, chosen so the store can be swapped for a server-backed one later without changing the conversation seam. Cross-thread long-term memory (a store) is deliberately not introduced.
- Clarification is an `interrupt` on the thread. Resuming supplies the analyst's choice and continues the pending analysis. Asking an unrelated question instead discards the pending clarification explicitly.
- Task fan-out for independent cells (company × metric × period) uses the graph's dynamic dispatch. Task semantics stay in the existing deterministic tool functions.
- A per-turn fact cache lives in run state so one analysis does not refetch the same company facts. Cached evidence reused on a later turn must be labelled as such in the result.

### Trust boundary

- Unchanged and restated: the model interprets language and proposes a patch; deterministic code owns fact selection, arithmetic, company identity, snapshot membership, workflow composition, and rendering of numbers.
- Ranked constituents come from the ranking port. A patch may request a ranked set; it may not enumerate one.
- The exploratory subgraph may choose among approved read-only capabilities and iterate, but its output is a labelled research draft with citations. It cannot emit structured financial rows, and it cannot introduce numerals absent from its evidence.
- Search stays the constrained news wrapper. No extract, crawl, or map. No second search vendor.
- Vendor figures, PDF parsing, and open web browsing remain outside the number path.

### Migration

- Step 1: introduce the graph as the private implementation of today's six workflows, with `run_turn` unchanged and the gold suite green. No new user-visible behaviour.
- Step 2: add the conversation seam and thread persistence, with `run_turn` delegating to an ephemeral thread.
- Step 3: introduce the analysis spec and patch resolution, expressed first as the existing workflows, then extended to multi-metric, multi-company, and multi-period composition.
- Step 4: convert clarification to a resumable interrupt and revise the affected decision record.
- Step 5: introduce the exploratory subgraph behind its label.
- Each step keeps the offline suite green and is independently revertible.

### Written record

Done before implementation; treat these as binding, not as pending work:

- ADR 0005 records the stateful thread plus patchable analysis spec, with the rejected alternatives (more closed intents, open ReAct, history-as-state, model-resolved spec, copied evidence, cross-thread memory, replacing `run_turn`) and the accepted costs.
- ADR 0004 is revised: the "hold a pending plan" rejection is marked superseded, and clarify is documented as a resumable interrupt. Its candidate-set rule and phrase table stand unchanged; chips stay rejected.
- The PRD is revised at the primary seam, the one-prompt-one-intent rule, the feature-seam testing note, and the multi-turn-memory out-of-scope entry. Open ReAct on the number path and LangGraph Studio as an audience surface stay out of scope.
- The glossary carries the new terms: conversation thread, analysis spec, spec patch, pending clarification, exploratory research. Existing terms (universe snapshot, snapshot member, operating company, quarterly fact, ambiguous metric, unknown metric) keep their current meanings.
- The design doc marks the shipped one-shot lifecycle as such and points its constrained-agency, application-interface, and clarify decisions at ADR 0005.

## Testing Decisions

Good tests assert observable behaviour at a seam: given a thread, a sequence of analyst messages, and a runtime, they assert the resulting spec, the workflow that ran, tool order, values, provenance, partial-row reasons, renderer choice, banners, and refusal or clarification state. They do not assert graph node names, channel names, checkpoint payload shapes, LangGraph internals, provider HTTP, or Streamlit widgets.

**Primary seam — the conversation entry point.** New behaviour is asserted here. Cases:

- A first message produces the expected resolved spec and result.
- A follow-up that adds a metric keeps the existing companies and periods.
- A follow-up that swaps a company keeps the existing metrics and operations.
- A follow-up that changes the period window re-runs the same metrics.
- An unrelated question replaces the spec rather than merging into it.
- A multi-company, multi-metric, multi-period request produces one analysis with the expected cells and typed reasons for missing ones.
- A ranked request feeds constituents from the ranking port, and a model-typed company list in the patch is ignored.
- An ambiguous metric interrupts with the colliding catalog names, runs no tools, and resumes the pending analysis when answered.
- An unknown metric refuses with the full allowed list.
- Asking something else while a clarification is pending discards it explicitly.
- Thread state round-trips: a new call with the same thread identifier sees the prior spec; a different identifier starts clean.
- Exploratory routing produces a labelled research result with citations and no structured financial rows.

**Existing seam — `run_turn`.** The gold tests and the per-intent `run_turn` tests stay as they are, with no assertion changes required by this spec, for the entire migration. They remain the guard on XBRL selection, `Decimal` formulas, period alignment, share-class consolidation, snapshot membership, numeral lock, and refusal catalogs. Prior art: the existing gold and per-intent suites.

**Internal unit seams.** Patch resolution, spec validation, and task compilation get focused unit tests: a patch applied to a spec yields the expected spec; an invalid patch yields the expected typed rejection; a resolved spec compiles to the expected task set without executing anything. Prior art: the existing metric phrase table and fact selector unit tests.

**Existing seam — presentation.** Formatting tests keep asserting display records without booting Streamlit. New result fields get cases here, not in the graph tests.

**Fixture runtime** remains how the offline suite and the kill-switch run. Persistence in tests uses a temporary durable store so thread round-trips are exercised rather than mocked. No test requires network unless network-marked.

## Out of Scope

- Open ReAct or model-chosen tool chaining on the number path.
- Model-performed arithmetic, valuation models, forecasts, or price targets.
- Cross-thread long-term memory, user preferences, or personalization.
- Multi-user accounts, authentication, authorization, or hosted deployment.
- New analyst capabilities: annual 10-K facts, balance-sheet and instant ratios, snapshot peers, filing narrative and MD&A retrieval, disclosure change maps, insider transactions, institutional holdings, exports, and scheduled recipes. This spec makes them cheap to add; it does not add them.
- Vendor figures, PDF parsing, or any second source of truth for quarterly numbers.
- Search beyond the constrained news wrapper.
- LangGraph Studio, a second client, or any audience surface other than the existing window.
- Replacing the presentation layer, restyling the window, or changing the MCP tool contracts.
- Charts and visualizations, beyond the spec carrying a requested presentation the renderer may ignore for now.
- Streaming as a product feature beyond progress visibility during a turn.

## Further Notes

The core bet is that flexibility belongs in the **domain language**, not in the agent's autonomy. A compositional analysis spec expresses "these companies, these metrics, these periods, these comparisons" without the model ever choosing a tool, a concept, or a number. Adding intents scales badly because combinations multiply; adding spec dimensions scales well because they multiply for free.

The persisted, patchable analysis spec is confirmed as the canonical representation of the analyst's current quantitative question. ADR 0005 is written and the affected records are revised, so implementation can start at migration step 1.

The known hazard of a patch-based interface is scoping a follow-up wrongly. "Add Apple" is unambiguous; "compare to last year" is not. An ambiguous patch must clarify rather than guess, and `extend` versus `replace` is a decision the system can now get wrong in a way one-shot turns could not. That belongs in the first round of conversation-seam tests, not in a later hardening pass.

The deterministic core is already the right shape for this. The runtime ports, the fact selector, the formula path, the ranking adapter, the numeral lock, and the presentation mapping all survive the redesign untouched. What changes is what sits above them.
