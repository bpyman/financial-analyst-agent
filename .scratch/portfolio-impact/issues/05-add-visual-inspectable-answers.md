# 05 — Add visual, inspectable answers

**What to build:** Structured answers lead with a chart or hero result, keep the exact table underneath, and let the analyst click any value to inspect the exact quarterly fact: raw amount, CIK, concept, period, accession, selection rule, and SEC filing link. Developer-heavy columns stay out of the default mobile view.

**Blocked by:** 04 — Create a guided first-run experience.

**Status:** resolved

- [x] Multi-period results show a line chart and cross-company results show a comparison chart, both sourced from the typed table.
- [x] Clicking a result opens an evidence inspector with the exact Decimal, identity, concept, period, accession, selection rule, and filing URL.
- [x] Opening the filing is a primary action, not a buried metadata string.
- [x] Answer, trust label, and traces appear in that order; traces remain expandable rather than competing with the answer.

## Answer

`present_turn` builds a `ChartSpec` from typed rows (line for multi-period, bar for cross-company). The inspector is a selectbox over `EvidenceItem` (exact Decimal, CIK, concept, period, accession, selection rule). `st.link_button("Open filing", ...)` is the primary filing action. CIK and taxonomy are omitted from the default table. Render order is chart/hero, table, inspector, trust banners, then expandable traces.

## Comments

- Agent: inspector uses a selectbox rather than dataframe cell clicks; the typed row is still the source of truth.
