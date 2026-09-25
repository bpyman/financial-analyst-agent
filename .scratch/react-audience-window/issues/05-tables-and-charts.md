# 05 — Comparisons and rankings render as tables and charts

**What to build:** Structured answers with more than one row render as a data table plus a chart. Examples: the four-quarter Microsoft trend, "add Apple", the Tesla/GM comparison, and the top-10 tech ranking with R&D.

- **Table.** Headers come from the server; identifier columns are hidden by default and the value column is right-aligned with tabular numerals. Source URLs become "Filing ↗" links. A compact/full switch reveals the provenance columns (currency, dates, form, accession, concept), with copy buttons on identifiers.
- **Trend charts** are lines per company, with period labels and tooltip amounts taken from the server.
- **Comparison charts** are bars. Ranked bars run horizontally in rank order, and missing values are shown muted with their reason.
- **Captions** appear under the chart. Axis ticks are compact dollar, percent, or multiple scales chosen by the chart's value kind.
- **Both themes.** Charts read clearly in dark and light.

Spec: ADR 0006 ("Presentation stays in Python").

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] "Compare four quarters" then "add Apple" shows a two-series line chart and a table with both companies
- [ ] "Rank then inspect filings" shows horizontal ranked bars, a snapshot banner, and a table with filing links
- [ ] Tooltip and table amounts match the server's formatted strings exactly
- [ ] Web lint, typecheck, unit tests, and production build pass
