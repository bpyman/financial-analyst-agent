# 05 — Add visual, inspectable answers

**What to build:** Structured answers lead with a chart or hero result, keep the exact table underneath, and let the analyst click any value to inspect the exact quarterly fact: raw amount, CIK, concept, period, accession, selection rule, and SEC filing link. Developer-heavy columns stay out of the default mobile view.

**Blocked by:** 04 — Create a guided first-run experience.

**Status:** ready-for-agent

- [ ] Multi-period results show a line chart and cross-company results show a comparison chart, both sourced from the typed table.
- [ ] Clicking a result opens an evidence inspector with the exact Decimal, identity, concept, period, accession, selection rule, and filing URL.
- [ ] Opening the filing is a primary action, not a buried metadata string.
- [ ] Answer, trust label, and traces appear in that order; traces remain expandable rather than competing with the answer.
