# 07 — Publish an evaluation and operability scorecard

**What to build:** The project can show, in numbers, that routing, identity, refusal, follow-ups, citations, and numeral lock behave as claimed. A checked-in scorecard reports pass rate, latency, approximate live cost, and the tested model. Structured logs correlate thread and turn with provider timing.

**Blocked by:** 02 — Add continuous verification; 03 — Make public sessions safe by default.

**Status:** ready-for-agent

- [ ] A versioned evaluation suite covers intent or spec-patch accuracy, issuer resolution, ambiguity and refusal, stateful follow-ups, citation coverage, numeral-lock violations, and fixture numeric correctness.
- [ ] A generated scorecard is published on the storefront with pass rate, p50/p95 latency, approximate cost per live scenario, and model version.
- [ ] Structured logs include thread and turn identifiers plus provider timing.
- [ ] SEC response caching and retry or rate-limit behavior are demonstrated and documented without claiming full production operations.
