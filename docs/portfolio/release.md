# Portfolio release notes

## LinkedIn post (draft)

I built a financial research agent that answers questions about public companies from their SEC filings, where the AI model is never allowed to touch the numbers.

Ask "Compare Eli Lilly and Pfizer revenue over the last eight quarters" and you get a chart where Lilly overtakes Pfizer in mid-2025. Every point on it comes from a 10-Q or 10-K, and one click shows the exact amount, the accession number, the XBRL concept, and a link to the filing.

A language model turns the question into a typed analysis plan. Deterministic Python fetches the quarterly facts from SEC EDGAR, derives fiscal Q4 from the 10-K when needed (and marks it), and computes margins, EBITDA, ROE and P/E in Decimal. Follow-ups like "add Apple" edit the analysis instead of starting over. "What changed in Microsoft's latest 10-Q?" returns a paragraph diff of MD&A and Risk Factors, not a model summary.

Try the demo (no sign-up): https://financial-analyst-agent-ten.vercel.app
Code: https://github.com/bpyman/financial-analyst-agent

Image: `images/social-preview.png`.

## Repository About

- Description: Ask about a public company, get the number and the SEC filing behind it. An evidence-first research agent: the LLM plans, deterministic code owns every figure.
- Website: https://financial-analyst-agent-ten.vercel.app
- Topics: sec, xbrl, edgar, financial-analysis, llm, ai-agent, langgraph, fastapi, nextjs, react, python, typescript, mcp, portfolio

## Visuals

Captured from the Next.js window on the recorded runtime, default dark theme, by `web/scripts/capture-portfolio.ts` (`cd web && npm run build && npm run capture`). Re-run it whenever the window changes.

1. GIF: [`docs/portfolio/images/demo-walkthrough.gif`](images/demo-walkthrough.gif) — Compare four quarters → `add Apple` → two-company chart → inspect the exact 10-Q source.
2. Walkthrough: [`docs/portfolio/images/demo-walkthrough.mp4`](images/demo-walkthrough.mp4) — the same walkthrough as H.264.
3. Screenshot: [`docs/portfolio/images/guided-first-run.png`](images/guided-first-run.png) — the landing page with the guided stories.
4. Screenshot: [`docs/portfolio/images/compare-four-quarters.png`](images/compare-four-quarters.png).
5. Screenshot: [`docs/portfolio/images/inspect-exact-source.png`](images/inspect-exact-source.png).
6. Screenshot: [`docs/portfolio/images/compare-lilly-pfizer.png`](images/compare-lilly-pfizer.png): "Compare Eli Lilly and Pfizer revenue over the last eight quarters", the README's hero.
7. Screenshot: [`docs/portfolio/images/filing-changes.png`](images/filing-changes.png): "What changed in Microsoft's latest 10-Q?", framed on the MD&A highlights.
8. GitHub social preview still: [`docs/portfolio/images/social-preview.png`](images/social-preview.png) (1280×640), the landing headline beside the Lilly vs Pfizer chart. Re-upload it in GitHub Settings → Social preview after a recapture.

The recorded runtime includes Apple quarterly revenue for its 10-Q periods. After a Microsoft four-quarter compare, `add Apple` still has no 10-Q on 2024-09-30 (Apple's fiscal year-end is a 10-K), so that cell stays `missing_fact` and the chart bridges the gap with a dotted line.
