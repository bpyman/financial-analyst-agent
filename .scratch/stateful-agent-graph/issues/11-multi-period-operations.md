# 11 — Multi-period analysis and across-period comparison

**Spec:** 01 — Stateful analysis graph

**What to build:** A trend as one request. The analysis spec's period selection carries a window, so "make that the last four quarters" re-runs the same metrics for the same companies across those periods, and a follow-up that widens or narrows the window leaves everything else alone.

Comparison becomes a spec operation rather than a new route. Across periods for one company gives sequential and year-over-year change; across companies for one period gives the cross-sectional view. Both are computed by deterministic formulas over period-aligned components using `Decimal`, so nothing is compared that is not comparable: mismatched periods do not compute, zero denominators return a typed non-compute result, and no model does arithmetic. Missing cells keep their typed reasons, so a four-quarter request with one unreported quarter still returns the other three.

**Blocked by:** 09, 10

**Status:** ready-for-agent

- [ ] A period window re-runs the active metrics across those periods as one analysis
- [ ] Changing the window keeps the existing companies, metrics, and operations
- [ ] Across-period comparison yields sequential and year-over-year change from period-aligned components
- [ ] Across-company comparison for a given period stays expressible
- [ ] Mismatched periods and zero denominators do not compute and say why
- [ ] A window with one unreported quarter returns the remaining cells with a typed reason for the gap
