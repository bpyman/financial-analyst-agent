# 09 — Multi-metric composition

**Spec:** 01 — Stateful analysis graph

**What to build:** One analysis covering several metrics at once, so "compare these two companies on revenue and operating margin" is a single request and "now add R&D intensity" widens a comparison the analyst already trusts. Removing a metric narrows a table that got too wide.

Every cell keeps its own provenance — the filing, accession, taxonomy, concept, and period behind a reported **quarterly fact**, or the components behind a formula, or the **universe snapshot** date behind a snapshot metric. Partial results are the rule: one absent fact leaves its cell empty with a typed reason and the rest of the table stands, and the reasons stay distinguishable so the analyst can tell a missing fact from a period mismatch from an ambiguous concept from a zero denominator. An unsupported combination is refused explicitly rather than quietly answered as something adjacent.

**Blocked by:** 03, 08

**Status:** resolved

- [x] One request covering several companies and several metrics produces one analysis with the expected cells
- [x] Adding a metric to the active analysis keeps the existing companies; removing one narrows the table
- [x] Every populated cell carries its own filing, formula-component, or snapshot provenance
- [x] A missing cell states its typed reason and does not sink the table
- [x] An unsupported combination refuses explicitly
- [x] Cells are compiled as independent tasks rather than special-cased per workflow

## Answer

Shipped multi-metric composition on the analysis-spec path. Metric binding accepts several unique phrases from the analyst's wording (no longer clarifies them away). `compile_tasks` emits one independent lookup/compare/rank_and_lookup task per metric; `run_spec_turn` executes them and merges rows, traces, and banners. Partial compare cells keep typed reasons (`missing_fact`, etc.) without sinking the table; multi-metric lookup refuses become partial cells when merging. Unsupported operations such as `across_periods` are a typed `unsupported_combination` rejection before providers. Follow-ups can add or remove metrics while keeping companies. Single-metric paths are unchanged.
