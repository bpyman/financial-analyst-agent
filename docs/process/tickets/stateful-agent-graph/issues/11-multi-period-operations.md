# 11 — Multi-period analysis and across-period comparison

**Spec:** 01 — Stateful analysis graph

**What to build:** A trend as one request. The analysis spec's period selection carries a window, so "make that the last four quarters" re-runs the same metrics for the same companies across those periods, and a follow-up that widens or narrows the window leaves everything else alone.

Comparison becomes a spec operation rather than a new route. Across periods for one company gives sequential and year-over-year change; across companies for one period gives the cross-sectional view. Both are computed by deterministic formulas over period-aligned components using `Decimal`, so nothing is compared that is not comparable: mismatched periods do not compute, zero denominators return a typed non-compute result, and no model does arithmetic. Missing cells keep their typed reasons, so a four-quarter request with one unreported quarter still returns the other three.

**Blocked by:** 09, 10

**Status:** resolved

- [x] A period window re-runs the active metrics across those periods as one analysis
- [x] Changing the window keeps the existing companies, metrics, and operations
- [x] Across-period comparison yields sequential and year-over-year change from period-aligned components
- [x] Across-company comparison for a given period stays expressible
- [x] Mismatched periods and zero denominators do not compute and say why
- [x] A window with one unreported quarter returns the remaining cells with a typed reason for the gap

## Answer

`PeriodSelection` supports `last_n_quarters` with `count` and optional concrete `report_dates` (newest first). `compile_tasks` fans out one lookup/compare task per report date; `set_periods` on an extend patch changes only the window. `across_periods` is a supported operation when the window has `count >= 2`; after level cells merge, deterministic `Decimal` subtraction emits sequential (adjacent) and YoY (same month/day prior year) rows with `TableRow.comparison` and two-period components. Across-company compare for a named period still uses `across_companies` + a one-date window via `report_date` on `compare_metrics` / lookup. Period mismatch and zero denominator stay typed non-compute reasons; a missing quarter in the window becomes a partial `missing_fact` cell. `list_quarterly_report_dates` on the filing selector / `SecFactLookup` supports discovery when dates are not yet concrete.
