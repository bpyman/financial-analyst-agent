# 12 — Recapture the portfolio images and rewrite the README for the new window

**What to build:** A Playwright capture script drives the compare-then-add-Apple walkthrough and inspects the exact 10-Q source. It saves the portfolio stills and a recording, converted to MP4 and GIF, replacing the Streamlit images, and can be re-run whenever the window changes.

The README describes the new window:
- badges and "Try it" point at the hosted demo, or a placeholder until ticket 11 records the URL;
- local run uses two commands;
- the architecture section names the Next.js window and the API seam;
- the Streamlit run instructions go.

Spec: ADR 0006 (cutover criteria).

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] The capture script runs against the recorded runtime and regenerates every README image
- [ ] The README has no Streamlit instructions and links ADR 0006
- [ ] The images show the new window in its default dark theme
