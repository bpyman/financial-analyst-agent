# 09 — Complete the flagship filing-change workflow

**What to build:** The filing-change path covers the reviewed section set, optionally summarizes only the selected diff under the numeral lock, and sits beside metric trends so one demo can move from a reported result to a trend to management disclosure to the exact source.

**Blocked by:** 07 — Publish an evaluation and operability scorecard; 08 — Ship a one-section filing-change tracer bullet.

**Status:** resolved

- [x] Multiple reviewed sections (at least MD&A and Risk Factors) can be compared for the same two accessions.
- [x] Any model summary is labelled analysis, grounded only in the produced diff, and fails the numeral lock if it invents numbers.
- [x] The same thread can show metric trends for the issuer alongside the disclosure map.
- [x] Evidence inspection works for both the numeric cells and the disclosure anchors.

## Answer

`parse_sections` can request both MD&A and Risk Factors for the same two accessions. Optional `summarize=True` runs the essay completer on the diff JSON, labels it model-analysis, and drops the essay if numeral lock extras appear. Filing-change turns keep the prior analysis spec, so a last-four-quarters lookup can sit on the same thread. Numeric cells use the evidence inspector; disclosure blocks have their own Open filing buttons.

## Comments

- Agent: fixture summary text is canned and number-free so the lock stays green.
