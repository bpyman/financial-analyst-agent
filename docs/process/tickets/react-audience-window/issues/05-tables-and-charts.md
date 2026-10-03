# 05 — Comparisons and rankings render as tables and charts

**What to build:** Structured answers with more than one row render as a data table plus a chart. Examples: the four-quarter Microsoft trend, "add Apple", the Tesla/GM comparison, and the top-10 tech ranking with R&D.

- **Table.** Headers come from the server; identifier columns are hidden by default and the value column is right-aligned with tabular numerals. Source URLs become "Filing ↗" links. A compact/full switch reveals the provenance columns (currency, dates, form, accession, concept), with copy buttons on identifiers.
- **Trend charts** are lines per company, with period labels and tooltip amounts taken from the server.
- **Comparison charts** are bars. Ranked bars run horizontally in rank order, and missing values are shown muted with their reason.
- **Captions** appear under the chart. Axis ticks are compact dollar, percent, or multiple scales chosen by the chart's value kind.
- **Both themes.** Charts read clearly in dark and light.

Spec: ADR 0006 ("Presentation stays in Python").

**Blocked by:** 04

**Status:** resolved

- [x] "Compare four quarters" then "add Apple" shows a two-series line chart and a table with both companies
- [x] "Rank then inspect filings" shows horizontal ranked bars, a snapshot banner, and a table with filing links
- [x] Tooltip and table amounts match the server's formatted strings exactly
- [x] Web lint, typecheck, unit tests, and production build pass

## Answer

Shipped 2026-09-25.

- `components/answer-chart.tsx` draws the server's chart record with Recharts. Trends are 2px lines per company with ringed 8px markers, clean 1-2-5 axis ticks, a two-line period axis, a legend for two or more series, the latest amount as an end label (hidden when two ends would collide), and a hover tooltip listing every series' server amount for that period. A quarter missing inside a series is bridged with a faint dotted line, not drawn as a value. Comparisons are columns; rankings are horizontal bars in rank order with "#n" and ticker in fixed columns. A missing value draws no bar, and its reason is written in muted italics where the bar would start. Captions sit under the chart. Bars and labels are drawn in one custom shape, because Recharts' LabelList put the labels after a zero-width bar on the wrong rows.
- `components/data-table.tsx` shows the server's headers and cells. Compact view: rank, company (ticker chip + name), value (right-aligned tabular numerals), end date, reason badge, and a "Filing ↗" link. Full view adds CIK, currency, start date, form, accession number, taxonomy, and concept, with copy buttons on CIK and accession number. The table scrolls sideways inside its card, never the page.
- `lib/table-view.ts` (column choice and roles) and `lib/chart-data.ts` (series keys and colours, rows, domains, nice ticks) are pure and unit-tested. Series get positional data keys, because a name like "Apple Inc." reads as a property path.
- Rank-and-lookup tables now carry `form`, `accession_number`, `concept`, and `source_url`, so "Rank then inspect filings" links each filing. Market-cap rankings stay as they were.
- The chart palette was re-ordered and the dark steps were moved into the dark lightness band, so adjacent colour-blind separation passes in both themes (checked with the dataviz validator).
- Checked in Chromium (dark and light, 1440px and 390px): every tooltip and table amount on the add-Apple walkthrough matches `presentation.chart.amounts` and the table rows exactly, and the page never scrolls sideways.
