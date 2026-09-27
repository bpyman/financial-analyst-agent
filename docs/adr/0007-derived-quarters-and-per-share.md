# Derived quarters, cash flow and per-share figures

> **Revises [ADR 0003](0003-quarterly-fact-module.md) and PRD story 43:** "no YTD subtraction, no derived Q4" becomes "derive only by the two rules below, label every derived value, and keep both filings as evidence". The no-float and no-model-math invariants stand.

Every multi-quarter window skipped fiscal fourth quarters, because companies report Q4 in the 10-K, and the 10-K tags the fiscal year, not the quarter. Cash flow could not be offered at all: a 10-Q reports operating cash flow and capital spending year to date (three, six, nine months), never for the quarter alone. Diluted EPS is reported per quarter in every 10-Q but was not in the catalog. Analysts expect all three, and the numbers they expect are the ones companies publish in their earnings releases, which are computed exactly this way.

## Decision

A **quarterly fact** is still preferred whenever the filing reports one. When it does not, deterministic code may derive a **derived quarter** by exactly one of two subtractions, both over directly reported XBRL facts in USD for the same concept:

1. **Fiscal fourth quarter.** Fiscal-year amount from the 10-K (duration 350 to 380 days, ending on the 10-K report date) minus the nine-month amount (duration 250 to 290 days) with the same start date, reported in a 10-Q.
2. **Year-to-date difference.** A cumulative amount from a 10-Q (duration over 110 days, ending on the 10-Q report date) minus the cumulative amount one quarter shorter with the same start date, reported in a 10-Q. This gives cash-flow quarters two and three.

Rules that keep this honest:

- The two facts must share a start date exactly (the fiscal-year start), so they cannot straddle a fiscal-year change or a restated period with new bounds. The shorter fact's end must fall 60 to 120 days before the longer fact's end.
- When several filings report the shorter amount (a later 10-Q repeats it as a comparative), the latest filed wins, as with any other fact. Conflicting same-day values raise `AmbiguousFactError`, never a pick.
- The derived fact has `directly_reported=False` and names both facts (value, dates, form, accession, concept, source URL). The table marks the value "Derived", its trace shows the subtraction, and both filings are evidence.
- A derived quarter never feeds another derivation.
- **Per-share figures are never derived.** Diluted EPS for a quarter is shown only when a filing reports it for that quarter. Annual EPS minus nine-month EPS is not fourth-quarter EPS, because the share count changes during the year. A fourth-quarter EPS cell says so rather than showing a blank.
- Formula metrics (margins, free cash flow) may use derived components; the row is derived if any component is.

New catalog entries:

| Metric | Concept (first match wins) | Unit | Quarter |
|---|---|---|---|
| `eps_diluted` | `EarningsPerShareDiluted` | USD/shares | reported only |
| `eps_basic` | `EarningsPerShareBasic` | USD/shares | reported only |
| `operating_cash_flow` | `NetCashProvidedByUsedInOperatingActivities` | USD | Q1 reported, Q2 to Q4 derived |
| `capital_expenditure` | `PaymentsToAcquirePropertyPlantAndEquipment`, `PaymentsToAcquireProductiveAssets` | USD | as above |
| `free_cash_flow` | formula: operating cash flow minus capital expenditure | USD | as its components |

**Latest quarter** now means the newest period any 10-Q or 10-K covers, so a question asked in the weeks after a 10-K is filed shows the fourth quarter instead of a quarter that is five months old. Windows list 10-K report dates beside 10-Q dates, so they no longer skip Q4.

**Named periods** ("Q3 2024", "fiscal 2025") are fiscal: they use the fiscal year and period each filing declares in its XBRL (`fy`, `fp`), which is how companies and the press name quarters. "Calendar Q3 2024" picks the quarter whose middle falls in that calendar quarter. Each company gets its own dates, and a banner says when same-named fiscal quarters end on different dates.

## Considered options

- **Keep refusing Q4 and cash flow.** Rejected: every window had a hole in it and a banner explaining the hole, and cash flow is one of the first things an analyst asks about.
- **Use the frames API (`CY2025Q4`).** Rejected: frames are calendar-aligned, deduplicated across filings, and drop the filing a number came from, so provenance would be weaker than it is today.
- **Derive per-share figures as annual minus nine months.** Rejected: that figure is wrong whenever the share count moved, and the error is silent.
- **Let the model compute derived values.** Rejected: model math stays forbidden. The subtraction is two Decimal facts in deterministic code.
