# Portfolio release notes

## LinkedIn post (draft)

An evidence-first financial research agent: it answers from SEC filings, and the language model never touches the numbers.

A planner proposes a typed analysis spec. Deterministic code resolves identity, picks the standalone 10-Q fact, does the arithmetic, and renders the table. Follow-ups patch the spec instead of restarting. Click any value to inspect the exact Decimal, CIK, concept, accession, and filing URL. Compare MD&A and Risk Factors between two accessions and you get a paragraph diff the model did not write.

Try the guided demo (recorded runtime, no keys): HOSTED_DEMO_URL <!-- ticket 11 fills in the *.vercel.app link -->
Repo: https://github.com/bpyman/financial-analyst-agent

## Visuals

Captured from the Next.js window on the recorded runtime, default dark theme, by `web/scripts/capture-portfolio.ts` (`cd web && npm run build && npm run capture`). Re-run it whenever the window changes.

1. GIF: [`docs/portfolio/images/demo-walkthrough.gif`](images/demo-walkthrough.gif) — Compare four quarters → `add Apple` → two-company chart → inspect the exact 10-Q source.
2. Walkthrough: [`docs/portfolio/images/demo-walkthrough.mp4`](images/demo-walkthrough.mp4) — the same walkthrough as H.264.
3. Screenshot: [`docs/portfolio/images/guided-first-run.png`](images/guided-first-run.png) — the landing page with the guided stories.
4. Screenshot: [`docs/portfolio/images/compare-four-quarters.png`](images/compare-four-quarters.png).
5. Screenshot: [`docs/portfolio/images/inspect-exact-source.png`](images/inspect-exact-source.png).
6. GitHub social preview still: [`docs/portfolio/images/social-preview.png`](images/social-preview.png) (1280×640). Re-upload it in GitHub Settings → Social preview after a recapture.

Repository homepage: HOSTED_DEMO_URL <!-- ticket 11 -->

The recorded runtime includes Apple quarterly revenue for its 10-Q periods. After a Microsoft four-quarter compare, `add Apple` still has no 10-Q on 2024-09-30 (Apple's fiscal year-end is a 10-K), so that cell stays `missing_fact` and the chart bridges the gap with a dotted line.
