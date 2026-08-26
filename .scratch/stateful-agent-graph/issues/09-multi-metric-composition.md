# 09 — Multi-metric composition

**Spec:** 01 — Stateful analysis graph

**What to build:** One analysis covering several metrics at once, so "compare these two companies on revenue and operating margin" is a single request and "now add R&D intensity" widens a comparison the analyst already trusts. Removing a metric narrows a table that got too wide.

Every cell keeps its own provenance — the filing, accession, taxonomy, concept, and period behind a reported **quarterly fact**, or the components behind a formula, or the **universe snapshot** date behind a snapshot metric. Partial results are the rule: one absent fact leaves its cell empty with a typed reason and the rest of the table stands, and the reasons stay distinguishable so the analyst can tell a missing fact from a period mismatch from an ambiguous concept from a zero denominator. An unsupported combination is refused explicitly rather than quietly answered as something adjacent.

**Blocked by:** 03, 08

**Status:** ready-for-agent

- [ ] One request covering several companies and several metrics produces one analysis with the expected cells
- [ ] Adding a metric to the active analysis keeps the existing companies; removing one narrows the table
- [ ] Every populated cell carries its own filing, formula-component, or snapshot provenance
- [ ] A missing cell states its typed reason and does not sink the table
- [ ] An unsupported combination refuses explicitly
- [ ] Cells are compiled as independent tasks rather than special-cased per workflow
