# 14 — Resumable clarification

**Spec:** 01 — Stateful analysis graph

**What to build:** An **ambiguous metric** asks one question and then gets on with the work. Today clarifying discards the planned analysis and the analyst retypes the whole request. Instead the analysis is held on the thread as a **pending clarification** — nothing fetched, no provider touched — and the analyst's answer resumes exactly the work that was planned before the question was asked.

The rules that make clarification trustworthy stand unchanged. The candidate set is the colliding closed-catalog names only, never a model-invented list. An **unknown metric** still refuses with the full allowed catalog, because clarification and refusal are distinct product states. And the analyst is never trapped: asking something unrelated while a clarification is pending discards it explicitly rather than folding the answer into the wrong question.

A patch-based interface can also mis-scope a follow-up. "Add Apple" is unambiguous; "compare to last year" is not. An ambiguous patch clarifies rather than guessing which way to read it.

**Blocked by:** 08

**Status:** resolved

- [x] An ambiguous metric holds the pending analysis and runs no tools
- [x] Answering the question resumes the pending analysis rather than requiring a retype
- [x] Candidates remain the colliding catalog names only
- [x] An unknown metric still refuses with the full allowed list
- [x] Asking something unrelated discards the pending clarification explicitly
- [x] An ambiguously scoped follow-up clarifies instead of guessing between extending and replacing

## Answer

Pending clarification is thread state. An ambiguous metric (or `SpecPatch.mode is None`) returns `CLARIFY` with catalog candidates, stores the proposed patch on the thread, and touches no providers. Answering with a unique candidate phrase (or `extend`/`replace`) resumes via `run_spec_turn` on the held patch. An unrelated message clears the pending interrupt and banners `Discarded pending clarification`. Unknown metrics still refuse with the full catalog and leave no pending.
