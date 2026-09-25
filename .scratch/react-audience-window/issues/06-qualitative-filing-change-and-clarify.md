# 06 — Qualitative answers, filing changes, and clarification

**What to build:** The remaining answer shapes render in the new window.

- **Qualitative answers.** Explain, current-events, and exploratory-research answers render their essay as safe markdown, with the model-analysis or exploratory banner and numbered citations linking to sources, plus publication dates.
- **Filing changes.** A filing-change answer ("What changed in the 10-Q") shows each changed section with its change kind, the previous and current filing text side by side (stacked on phones), and links to both filings.
- **Clarification.** An ambiguous metric or ambiguous extend/replace scope shows the clarify prompt with one button per candidate. A button sends the candidate's catalog slug as the next analyst message. Only the latest turn's buttons are live, and only while the thread holds a pending clarification; older ones render disabled.

Spec: ADR 0006 ("Clarify answers are messages"), ADR 0004, ADR 0005.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] "What changed in the 10-Q" shows both sections with before/after text and filing links
- [ ] "What was Google's latest quarterly profit?" offers Gross profit, Operating income, and Net income; clicking Net income resumes and shows the fact card, and the earlier buttons turn disabled
- [ ] Essay markdown cannot inject script or unsafe links
- [ ] Web lint, typecheck, unit tests, and production build pass
