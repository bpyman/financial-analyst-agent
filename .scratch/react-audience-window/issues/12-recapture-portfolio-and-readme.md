# 12 — Recapture the portfolio images and rewrite the README for the new window

**What to build:** A Playwright capture script drives the compare-then-add-Apple walkthrough and inspects the exact 10-Q source. It saves the portfolio stills and a recording, converted to MP4 and GIF, replacing the Streamlit images, and can be re-run whenever the window changes.

The README describes the new window:
- badges and "Try it" point at the hosted demo, or a placeholder until ticket 11 records the URL;
- local run uses two commands;
- the architecture section names the Next.js window and the API seam;
- the Streamlit run instructions go.

Spec: ADR 0006 (cutover criteria).

**Blocked by:** 07

**Status:** resolved

- [x] The capture script runs against the recorded runtime and regenerates every README image
- [x] The README has no Streamlit instructions and links ADR 0006
- [x] The images show the new window in its default dark theme

## Answer

Shipped on `claude/epic-curie-qabi6r-cutover` (PR 3).

- `web/scripts/capture-portfolio.ts` is a Playwright script with its own config (`web/playwright.capture.config.ts`, reusing the browser check's recorded API and built-app servers, or `PLAYWRIGHT_BASE_URL`). Run it with `cd web && npm run build && npm run capture`. On one fresh thread at 2x (1280×1000 CSS) it takes `guided-first-run.png`, `compare-four-quarters.png` (Compare four quarters), `social-preview.png` (1280×640, the two-company chart after `add Apple`), and `inspect-exact-source.png` (the evidence inspector on Apple's standalone 10-Q fact). On a second thread it records the walkthrough (1280×800, with a drawn cursor, since headless recordings have none): Compare four quarters, a sweep of the chart tooltip, the table, typing `add Apple`, the two-company chart, then the inspector's Apple fact and Open filing. ffmpeg turns the recording into `demo-walkthrough.mp4` (H.264, about 1.2 MB) and `demo-walkthrough.gif` (880 px, 8 fps, 64 colours, about 4.6 MB). The page-load frames are trimmed off.
- ffmpeg comes from `$FFMPEG` or `ffmpeg` on PATH. The run fails before opening a browser, with a fix-it message, if neither works. The command builders and the lookup live in `web/scripts/portfolio-media.ts` and are unit-tested.
- All six files in `docs/portfolio/images/` were regenerated from the Next.js window in the default dark theme, and each was reviewed by eye. No Streamlit image remains.
- README: new badges (Next.js, plus a grey "demo: coming soon" badge), a "Try it" section, "Run it locally" (one-time setup, then two commands: `uv run serve-api` and `npm --prefix web run dev`), "Deploy", an Architecture section that names the Next.js window, the `/api/*` proxy, and the FastAPI seam over the conversation seam and `present_turn`, with ADR 0006 linked, and "Portfolio images". No Streamlit instructions remain. `tests/test_readme.py` pins that, the ADR link, the media existing, and the capture script writing every portfolio file.
- **Hosted URL placeholder (ticket 11):** the hosted URL does not exist yet. To fill it in, search for `HOSTED_DEMO_URL`. It appears in README.md twice (HTML comments above the demo badge and in "Try it"; replace the badge target `#try-it` and the "coming soon on Vercel" sentence) and in `docs/portfolio/release.md` twice (the LinkedIn draft and "Repository homepage"). The README test accepts either the marker or a `https://*.vercel.app` link. After ticket 11, also re-upload `social-preview.png` in GitHub Settings → Social preview.
