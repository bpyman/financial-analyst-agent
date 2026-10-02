# Portfolio release notes

## LinkedIn post (draft)

Attach `images/demo-walkthrough.mp4` (34 s, no sound needed). Its first frame is the landing page headline, which works as the cover.

I built Onfile: ask about a public company in plain English and get the number and the SEC filing behind it. The AI model plans the question; it is never allowed to touch the numbers.

In the video I ask for Eli Lilly, Pfizer and Merck revenue over the last eight quarters, then type "show year-over-year". The same analysis redraws as growth rates: in the latest quarter Lilly grew 47.7%, Merck 5.1% and Pfizer 2.6%. Then one click shows where Lilly's $22.97B came from: the exact amount, the 10-Q's accession number, the XBRL concept, and a link to the filing.

How it works: a language model turns the question into a typed analysis plan. Deterministic Python fetches the quarterly facts from SEC EDGAR, derives fiscal Q4 from the 10-K when needed (and marks it), lines up companies whose fiscal quarters end on different dates, and computes margins, growth, EBITDA, ROE and P/E. The model never writes a figure.

It also sorts tables by any column (the chart follows), and "What changed in Microsoft's latest 10-Q?" returns a paragraph diff of MD&A and Risk Factors with the changed words marked, not a model summary.

I checked it two ways, and both are in the repo. I took 25 figures the app shows, across sectors, and found every one in the text of the 10-Q it cites. And a set of 30 test questions (lookups, follow-ups, refusals, fiscal calendars, rankings) passes in full.

What it doesn't cover yet: subsidiaries that file jointly with their parent have no quarterly figures of their own in SEC's data, foreign companies that file 20-Fs are out of scope, and market caps come from a dated snapshot.

Try the demo (no sign-up): https://onfile-analyst.vercel.app
Code: https://github.com/bpyman/onfile

Feedback welcome, especially from anyone who reads filings for a living.

## Repository About

- Description: Ask about a public company, get the number and the SEC filing behind it. An evidence-first research agent: the LLM plans, deterministic code owns every figure.
- Website: https://onfile-analyst.vercel.app
- Topics: ai-agent, edgar, sec-edgar, xbrl, financial-analysis, fastapi, langgraph-python, llm, mcp, nextjs, react, typescript, python3, portfolio-project
- Social preview (Settings → General → Social preview, upload only): `images/social-preview.png`

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
10. GitHub social preview still: [`docs/portfolio/images/social-preview.png`](images/social-preview.png) (1200×628), the landing headline beside the Lilly vs Pfizer chart, with each company's latest figure above it. Re-upload it in GitHub Settings → Social preview after a recapture.

The recorded runtime includes Apple quarterly revenue for its 10-Q periods. After a Microsoft four-quarter compare, `add Apple` still has no 10-Q on 2024-09-30 (Apple's fiscal year-end is a 10-K), so that cell stays `missing_fact` and the chart bridges the gap with a dotted line.
