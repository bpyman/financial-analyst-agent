# 03 — Resolve metric phrases per phrase, not per question

**Spec:** 01 — Stateful analysis graph

**What to build:** Metric resolution currently reports a question as an **ambiguous metric** whenever it finds two different catalog names in it, so "revenue and operating margin" is treated as a collision rather than as two metrics. That reading has to change before an analysis spec can hold more than one metric. Resolve the ordered set of metric phrases a question contains, classifying each phrase on its own as a catalog name, an ambiguous metric, or an unknown metric. Resolution keeps running on the analyst's wording, not on a model-supplied slug.

Single-phrase behaviour must not move: a question naming one metric resolves exactly as it does today, a colliding phrase still clarifies with the same candidate names, and a phrase naming nothing in the closed catalog is still unknown.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A question naming several distinct catalog metrics resolves to those metrics in order, not to an ambiguous metric
- [ ] A colliding phrase is still ambiguous, with the same candidate set, even when it sits beside a phrase that resolves cleanly
- [ ] A phrase naming nothing in the closed catalog is still unknown
- [ ] Existing single-metric clarify and refusal behaviour is unchanged at the application seam
- [ ] The phrase table gets unit cases in the style of the existing ones
