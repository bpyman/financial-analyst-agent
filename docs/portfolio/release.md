# Portfolio release notes

## LinkedIn post (draft)

I built Onfile: ask about a public company and get the number and the SEC filing behind it. The AI model plans the question; it is never allowed to touch the numbers.

Ask "Compare Eli Lilly and Pfizer revenue over the last eight quarters" and you get a chart where Lilly overtakes Pfizer in mid-2025. Every point on it comes from a 10-Q or 10-K, and one click shows the exact amount, the accession number, the XBRL concept, and a link to the filing.

A language model turns the question into a typed analysis plan. Deterministic Python fetches the quarterly facts from SEC EDGAR, derives fiscal Q4 from the 10-K when needed (and marks it), lines up companies whose fiscal quarters end on different dates, and computes margins, growth, EBITDA, ROE and P/E in Decimal. Follow-ups like "add Apple" or "show year-over-year" edit the analysis instead of starting over. Tables sort by any column and the chart follows. "What changed in Microsoft's latest 10-Q?" returns a paragraph diff of MD&A and Risk Factors with the changed words marked, not a model summary.

To check it, I took 25 figures the app shows across sectors and found every one in the text of the 10-Q it cites. The 30-case scorecard and that check are in the repo.

What it doesn't cover yet: subsidiaries that file jointly with their parent have no quarterly figures of their own in SEC's data, foreign companies that file 20-Fs are out of scope, and market caps come from a dated snapshot.

Try the demo (no sign-up): https://onfile-analyst.vercel.app
Code: https://github.com/bpyman/onfile

Feedback welcome, especially from anyone who reads filings for a living.

Image: `images/social-preview.png`.

## Repository About

- Description: Financial research from SEC filings. Ask about a public company, get the number and the filing behind it; the LLM plans, deterministic code owns every figure.
- Website: https://onfile-analyst.vercel.app
- Topics: sec, xbrl, edgar, financial-analysis, llm, ai-agent, langgraph, fastapi, nextjs, react, python, typescript, mcp, portfolio

## Visuals

Captured from the Next.js window on the recorded runtime, default dark theme, by `web/scripts/capture-portfolio.ts` (`cd web && npm run build && npm run capture`). Re-run it whenever the window changes.

1. GIF: [`docs/portfolio/images/demo-walkthrough.gif`](images/demo-walkthrough.gif) — Eli Lilly, Pfizer and Merck revenue → `show year-over-year` → growth chart → inspect the exact 10-Q source.
2. Walkthrough: [`docs/portfolio/images/demo-walkthrough.mp4`](images/demo-walkthrough.mp4) — the same walkthrough as H.264.
3. Screenshot: [`docs/portfolio/images/guided-first-run.png`](images/guided-first-run.png) — the landing page with the guided stories.
4. Screenshot: [`docs/portfolio/images/compare-four-quarters.png`](images/compare-four-quarters.png).
5. Screenshot: [`docs/portfolio/images/inspect-exact-source.png`](images/inspect-exact-source.png).
6. Screenshot: [`docs/portfolio/images/compare-lilly-pfizer.png`](images/compare-lilly-pfizer.png): "Compare Eli Lilly and Pfizer revenue over the last eight quarters", the README's hero.
7. Screenshot: [`docs/portfolio/images/filing-changes.png`](images/filing-changes.png): "What changed in Microsoft's latest 10-Q?", framed on the MD&A highlights.
8. Screenshot: [`docs/portfolio/images/overview-trends.png`](images/overview-trends.png): "How is Nvidia doing?", a sentence, then revenue and net-margin trends over five quarters.
9. Screenshot: [`docs/portfolio/images/sorted-ranking.png`](images/sorted-ranking.png): the top 10 tech companies re-sorted by R&D, the chart's bars following the table.
10. GitHub social preview still: [`docs/portfolio/images/social-preview.png`](images/social-preview.png) (1280×640), the landing headline beside the Lilly vs Pfizer chart. Re-upload it in GitHub Settings → Social preview after a recapture.

The recorded runtime includes Apple quarterly revenue for its 10-Q periods. After a Microsoft four-quarter compare, `add Apple` still has no 10-Q on 2024-09-30 (Apple's fiscal year-end is a 10-K), so that cell stays `missing_fact` and the chart bridges the gap with a dotted line.
