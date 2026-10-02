# 07 — A browser check in CI guards the window

**What to build:** CI proves the window works end to end, replacing what the Streamlit window tests guarded. A new CI job, on Node 22 (pinned for the repo), runs:
- web lint, typecheck, unit tests, and production build;
- a Playwright check that starts the API in the recorded runtime and the built web app;
- in the Playwright check: each guided story, checking for its fact card, chart, table, or disclosure;
- the compare-then-add-Apple walkthrough;
- the clarify-button round trip;
- Start over.

The Playwright check takes a base URL, so the same suite can later run against the hosted demo. The existing Python job stays as it is.

Spec: ADR 0006 (cutover criteria).

**Blocked by:** 05, 06

**Status:** resolved

- [x] The Playwright suite passes locally against the recorded runtime
- [x] The CI workflow has a web job that installs from the lockfile and runs all checks; Python checks unchanged
- [x] Selectors use roles and labels, not CSS internals
- [x] The suite can target another base URL through an environment variable

## Answer

- **Browser check.** `web/e2e/window.spec.ts` (Playwright, `@playwright/test` pinned to 1.56.1) has seven tests, each on a fresh browser context and so a fresh thread: the four guided stories (the Microsoft fact card with its filing link and the evidence inspector; the four-quarter trend chart and a 4-row table; the ten-company ranking with a chart, 10 filing links, and the Full column switch showing accession numbers; the MD&A and Risk Factors filing-change articles with their previous-filing links), compare four quarters then "add Apple" (a second chart whose legend reads Microsoft then Apple, AAPL in Active analysis, 2 turns used), the clarify round trip (Gross profit / Operating income / Net income, click Net income, a Net income fact card, the old buttons disabled and "Answered below.", the bubble reads "Net income" and was sent as `net_income`), and reload resumes the thread, then Start over clears it and a second reload stays clear.
- **Selectors.** `web/e2e/analyst.ts` is the page object: roles and accessible names only (regions, figure, rows, links, radios, the "Turns used" counter, the composer textbox, and `getByTitle` for "Sent as net_income"). A turn is finished when the counter reaches the next count and the send button reads "Send" again.
- **Servers and base URL.** `web/playwright.config.ts` starts `uv run serve-api` from the repo root (`APP_MODE=recorded`, `PUBLIC_DEMO=false`, and an empty `API_PROXY_TOKEN`, so a developer's `.env` cannot change the runtime) on port 8100, and `npm start` on port 3100 with `API_ORIGIN` pointed at it. Outside CI it reuses servers already running. `PLAYWRIGHT_BASE_URL` skips both and targets a deployed window, with 2 workers and 90 s expect timeouts for a slow hosted tier.
- **CI.** `.github/workflows/ci.yml` gains a `web` job: Node from `.nvmrc` (22) with the npm cache, `npm ci`, lint, `npm test` (vitest), build, `tsc --noEmit` (after the build, which writes `next-env.d.ts`), uv + Python 3.12 and `uv sync`, `npx playwright install --with-deps chromium`, `npm run test:e2e`, and the HTML report uploaded on failure. The Python `check` job is unchanged.
- Node 22 is pinned by `.nvmrc` and `engines: {"node": "22.x"}`. `web/vitest.config.ts` keeps `e2e/` out of vitest. `npm test` and `npm run test:e2e` are new scripts.
- Verified red: with the chart removed and clarify buttons forced dead, 4 of 7 tests fail. The CI steps were run in a clean copy of the tree (fresh `npm ci`, no `.next`, no `.cache`) with `CI=true`, and the suite also passed against servers started by hand via `PLAYWRIGHT_BASE_URL`.
