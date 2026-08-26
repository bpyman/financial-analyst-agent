# 12 — Concurrent dispatch and visible progress

**Spec:** 01 — Stateful analysis graph

**What to build:** A wide analysis that finishes in reasonable time and never looks hung. Eight quarters times four metrics is thirty-two independent cells; run them concurrently instead of one round trip after another. While a turn is working, the analyst sees progress rather than an indefinite spinner.

Concurrency must not change a single number. The same request produces the same values, provenance, and row order as the serial path, because task semantics stay in the existing deterministic tool functions and only their dispatch changes. Failure is isolated the same way: a provider error fails that cell with its typed reason and leaves the rest of the analysis and the **conversation thread** intact. Streaming exists here only to make a long turn legible, not as a product surface.

**Blocked by:** 11

**Status:** ready-for-agent

- [ ] Independent cells in one analysis execute concurrently
- [ ] A wide analysis returns the same values, provenance, and ordering as serial execution against the fixture runtime
- [ ] A failed provider call fails one cell with its typed reason and does not fail the turn or the thread
- [ ] Progress is visible while a long turn runs
- [ ] Concurrency is bounded so a wide request cannot flood a provider
