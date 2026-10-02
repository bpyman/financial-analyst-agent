# 05 — Run the qualitative workflows on the graph

**Spec:** 01 — Stateful analysis graph

**What to build:** The remaining two answers — qualitative explanation and current events — move onto the graph as their own subgraphs, so the application seam delegates all six workflows and the pre-graph dispatch is deleted. One path, not two.

Everything that makes those answers trustworthy stays put: the model-analysis banner on an explanation, bounded news search behind the constrained wrapper, citations on a current-events answer, refusal rather than training-data fallback when no usable news comes back, and the numeral lock rejecting any numeric token absent from the evidence the essay was given. Each subgraph takes its request and returns typed results; neither reads conversation history. The MCP tool contracts do not change.

**Blocked by:** 04

**Status:** resolved

- [x] Qualitative explanation and current events run as subgraphs, and the application seam delegates all six workflows
- [x] The pre-graph dispatch path is gone, so no workflow has two implementations
- [x] Banner, citation, numeral-lock, and news-refusal behaviour is unchanged
- [x] Subgraphs expose a small typed interface and do not read conversation history
- [x] The gold suite and per-workflow seam tests pass with no assertion changes

## Answer

Migration step 2: `run_qualitative_explanation` and `run_current_events` are one-node subgraphs behind typed interfaces; the parent graph routes all six closed intents via `run_workflow_turn`. `run_turn` delegates explain and news-and-explain through that entry (no direct helper calls). Banner, citations, numeral lock, and empty-news refuse stay in the existing turn helpers. Seam tests assert TurnResult only — no graph internals. `run_structured_turn` remains as a thin alias for structured callers.
