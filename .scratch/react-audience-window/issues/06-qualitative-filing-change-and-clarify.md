# 06 — Qualitative answers, filing changes, and clarification

**What to build:** The remaining answer shapes render in the new window.

- **Qualitative answers.** Explain, current-events, and exploratory-research answers render their essay as safe markdown, with the model-analysis or exploratory banner and numbered citations linking to sources, plus publication dates.
- **Filing changes.** A filing-change answer ("What changed in the 10-Q") shows each changed section with its change kind, the previous and current filing text side by side (stacked on phones), and links to both filings.
- **Clarification.** An ambiguous metric or ambiguous extend/replace scope shows the clarify prompt with one button per candidate. A button sends the candidate's catalog slug as the next analyst message. Only the latest turn's buttons are live, and only while the thread holds a pending clarification; older ones render disabled.

Spec: ADR 0006 ("Clarify answers are messages"), ADR 0004, ADR 0005.

**Blocked by:** 04

**Status:** resolved

- [x] "What changed in the 10-Q" shows both sections with before/after text and filing links
- [x] "What was Google's latest quarterly profit?" offers Gross profit, Operating income, and Net income; clicking Net income resumes and shows the fact card, and the earlier buttons turn disabled
- [x] Essay markdown cannot inject script or unsafe links
- [x] Web lint, typecheck, unit tests, and production build pass

## Answer

Shipped 2026-09-25.

- **Qualitative answers.** `components/written-answer.tsx` draws the essay through `components/markdown.tsx` (`SafeMarkdown`): raw HTML is skipped, images draw as alt text, and only http(s) links render. `[n]` markers become chips linking to citation n (`lib/essay.ts`), and a numbered Sources list shows each title, site, and publication date. The server now turns the `model-analysis` and `exploratory-research` banner codes into sentences (`presentation._BANNER_COPY`), so Streamlit and the new window both show readable banners.
- **Filing changes.** `components/filing-changes.tsx` shows the accession range, then one card per section with its change kind badge (added / removed / changed), previous and current text side by side (stacked below `md`), and "Open previous filing" / "Open current filing" links. A filing-change summary essay renders above the cards as "Summary of changes".
- **Clarification.** `Presentation.clarify_prompt` carries the question ("Which metric do you mean?" or "Add to the current analysis, or start a new one?"); Streamlit uses it too. `components/clarify.tsx` draws one button per candidate, labelled by the server with the slug beneath it. A button sends the slug via the window's `send`. Buttons are live only when `turn.clarify_enabled` and no turn is running. Once answered, the chosen candidate is ticked and the others are dimmed (`lib/clarify.ts`), and the answer bubble reads as the label ("Net income"), with the slug in its tooltip.
- `.prose-answer` moved into `@layer components` so caller colour utilities win.

