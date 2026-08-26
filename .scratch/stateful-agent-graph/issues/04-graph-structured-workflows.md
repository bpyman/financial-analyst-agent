# 04 — Run today's structured workflows on the graph

**Spec:** 01 — Stateful analysis graph

**What to build:** The same four structured answers as today, produced by a typed graph instead of a chain of conditionals. Add LangGraph and a parent graph whose edges are fixed and typed, with the quarterly lookup, comparison, ranking, and rank-then-lookup workflows executing as nodes that call the existing deterministic tool functions unchanged. The application seam delegates those four workflows to the graph and returns the identical result shape.

No new analyst-visible behaviour. This is migration step one, and its whole point is that the regression net cannot tell the difference: fact selection, `Decimal` formulas, period alignment, share-class consolidation, **universe snapshot** membership, partial-row reasons, and refusal catalogs all still come from the same code. Graph node names, channel names, and edge lists are implementation detail and are not asserted anywhere.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Quarterly lookup, comparison, ranking, and rank-then-lookup run through the graph
- [ ] The application seam returns the same intent, tool order, values, provenance, banners, and reasons as before
- [ ] The gold suite and the per-workflow seam tests pass with no assertion changes
- [ ] The model still selects a workflow from the closed set; it does not select nodes or chain tools
- [ ] No test asserts graph internals
