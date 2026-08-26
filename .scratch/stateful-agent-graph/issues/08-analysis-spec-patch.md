# 08 — Analysis spec and patch resolution

**Spec:** 01 — Stateful analysis graph

**What to build:** The first follow-ups that edit an analysis instead of restarting one. The thread's quantitative state becomes one **analysis spec** — companies or snapshot-derived constituents, closed-catalog metrics, a period selection, operations, and a requested presentation. A turn is a **spec patch**: the model proposes additions, removals, and replacements plus whether this turn extends or replaces the current analysis, and deterministic code applies the patch, resolves it to CIKs and catalog slugs, validates it against the closed catalogs, and compiles it into typed tasks. An invalid patch is a typed rejection before any provider call, not a best-effort fetch.

For a single metric this reproduces today's answers and adds real editing: "use Apple instead of Google" keeps the rest of the analysis, "add Nvidia" widens the company set, dropping a company narrows it, and an unrelated question replaces the spec rather than merging into it. What is currently active — companies, metrics, periods, operations — is visible, so the analyst knows what the next follow-up will edit.

The trust boundary does not move. The model never emits a resolved spec, never enumerates constituents (a ranked set comes from the ranking port, and a model-typed company list is ignored), never picks a concept, and never does arithmetic. Metric resolution still runs on the analyst's wording. The model's proposal is recorded separately from the resolved spec so both can be shown.

**Blocked by:** 06

**Status:** resolved

- [x] A first message produces the expected resolved spec and the same answer as today for one metric
- [x] Swapping, adding, and removing a company keeps the rest of the analysis intact
- [x] An unrelated question replaces the spec instead of merging into it
- [x] A spec is resolved and validated before any provider call, and an invalid patch is a typed rejection
- [x] A ranked request takes its constituents from the ranking port, and a model-typed company list is ignored
- [x] The active companies, metrics, periods, and operations are visible to the analyst
- [x] The model's proposed patch is recorded separately from the resolved spec
- [x] Patch application, spec validation, and task compilation have their own unit cases, including compiling without executing

## Answer

Shipped a patchable **analysis spec** on the conversation thread. Completer proposals are either a `SpecPatch` or a closed Plan lifted to replace-mode; deterministic code applies the patch, binds metrics from the analyst's wording, resolves identity / ranked constituents, validates against the closed catalogs, compiles typed tasks, and executes through the existing workflow graph. Invalid patches and unknown industries refuse with empty tool traces. `ConversationTurn` exposes `analysis_spec` and `proposed_patch`; only the resolved spec is persisted on `ThreadState` (proposed patch stays run-state). Qualitative turns clear the active spec. Single-metric lookup/compare/rank answers match today's paths; follow-ups can swap/add/remove companies without retyping the metric.
