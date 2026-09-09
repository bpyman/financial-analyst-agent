# 08 — Ship a one-section filing-change tracer bullet

**What to build:** An analyst can ask what changed in one reviewed section between two explicit filings for one company and see a deterministic added/removed/changed view with exact filing anchors, inspectable from the same evidence surface as quarterly facts.

**Blocked by:** 05 — Add visual, inspectable answers.

**Status:** ready-for-agent

- [ ] One company, two explicit accessions, and one reviewed section (MD&A or Risk Factors) produce a side-by-side change map.
- [ ] Section identity, accession choice, and the text diff are deterministic; the model does not pick filings or rewrite the diff.
- [ ] Each changed block has an exact filing anchor the evidence inspector can open.
- [ ] The tracer is demoable from the audience window without the later multi-section summary.
