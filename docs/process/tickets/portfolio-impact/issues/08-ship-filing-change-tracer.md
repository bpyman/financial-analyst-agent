# 08 — Ship a one-section filing-change tracer bullet

**What to build:** An analyst can ask what changed in one reviewed section between two explicit filings for one company and see a deterministic added/removed/changed view with exact filing anchors, inspectable from the same evidence surface as quarterly facts.

**Blocked by:** 05 — Add visual, inspectable answers.

**Status:** resolved

- [x] One company, two explicit accessions, and one reviewed section (MD&A or Risk Factors) produce a side-by-side change map.
- [x] Section identity, accession choice, and the text diff are deterministic; the model does not pick filings or rewrite the diff.
- [x] Each changed block has an exact filing anchor the evidence inspector can open.
- [x] The tracer is demoable from the audience window without the later multi-section summary.

## Answer

`Intent.FILING_CHANGE` plus `run_filing_change` extract Item 2/7 (MD&A) or Item 1A (Risk Factors) from accession-pinned HTML and diff paragraphs with `difflib`. The planner/demo completer does not choose filings. Each `DisclosureChange` has previous/current filing URLs opened via `st.link_button`. The empty-chat story "What changed in the 10-Q" runs the fixture Microsoft pair.

## Comments

- Agent: fixture HTML is in `sec_fixture_recordings.json` under `filing_documents`.
