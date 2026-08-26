# 13 — Evidence on the thread, referenced not copied

**Spec:** 01 — Stateful analysis graph

**What to build:** The evidence behind the current analysis stays available to the next turn. Fetched facts, news hits, and computed results are addressed by identifier and referenced from thread state, so a follow-up that widens a comparison reuses what was already retrieved instead of refetching it, and a later qualitative question is grounded in the same numbers the analyst is looking at rather than in a fresh guess.

Two constraints make this safe. Reuse is labelled: anything served from thread evidence says so, so freshness is never implied by a stale value. And evidence is referenced rather than copied into every checkpoint, so thread state does not grow without bound as an investigation goes on.

**Blocked by:** 09

**Status:** resolved

- [x] Facts, news hits, and results are addressed by identifier and referenced from thread state, not copied into it
- [x] A follow-up reuses retained evidence instead of refetching it
- [x] Any value served from thread evidence is labelled as such in the result
- [x] A qualitative question after an analysis receives the already-computed deterministic result
- [x] Thread state stays small as turns accumulate

## Answer

Shipped a per-thread **evidence store** separate from thread checkpoints. Facts (stable cell ids), news hits (by URL), and turn results live in `LocalEvidenceStore` / `InMemoryEvidenceStore`; `ThreadState` keeps only `evidence_refs` and `last_result_ref`. The conversation seam wraps `FactsPort` with `EvidenceCachedFacts` so follow-ups reuse prior cells without refetching and label the turn with `Reused thread evidence`. Qualitative turns receive the prior deterministic result as `grounding_json` for the essay / numeral lock. Subgraphs still do not read conversation history — grounding is injected at the parent seam.
