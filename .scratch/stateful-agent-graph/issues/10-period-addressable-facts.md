# 10 — Period-addressable quarterly facts

**Spec:** 01 — Stateful analysis graph

**What to build:** Ask for a specific quarter, not only the most recent one. Fact lookup can currently answer "the latest quarterly revenue" and nothing else, which is the floor under any trend or year-over-year question. Extend the fact capability so a named quarter is addressable, and the answer is the directly reported standalone-quarter amount for that period with provenance pointing at the filing it actually came from.

The selection rules do not loosen. Still a standalone-quarter duration from a quarterly filing, still no year-to-date subtraction, still no derived Q4, still a typed failure when candidate concepts collide, and still a typed failure when the requested quarter is not reported rather than the nearest available period silently standing in for it. Latest-quarter behaviour is unchanged for every existing caller.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] A named quarter can be requested and returns that quarter's directly reported amount with correct filing provenance
- [ ] Latest-quarter lookups behave exactly as they do today
- [ ] Standalone-duration rules hold, with no year-to-date subtraction and no derived Q4
- [ ] A requested quarter that is not reported is a typed failure, never a substituted neighbouring period
- [ ] Colliding candidate concepts still fail as an ambiguous concept
- [ ] Period selection has unit cases at the fact-selection seam
