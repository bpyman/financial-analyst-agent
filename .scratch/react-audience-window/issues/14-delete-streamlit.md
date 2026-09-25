# 14 — Delete the Streamlit window

**What to build:** Once the new window is live, `main` sheds Streamlit:
- the Streamlit app and its tests;
- the Streamlit settings and secrets example;
- the Community Cloud requirements export;
- the `streamlit`, `streamlit-shadcn-ui`, `altair`, and `pandas` dependencies.

Storefront copy, session budget, and presentation stay, because the API uses them. The PRD notes that ADR 0006 supersedes its "Streamlit is the only audience window" story.

The PR carrying this ticket stays a draft until ticket 11 is resolved. Merging it is the cutover.

Spec: ADR 0006 (Migration, cutover criteria).

**Blocked by:** 12, 13

**Status:** ready-for-agent

- [ ] Nothing in `src/`, `tests/`, or the dependencies imports Streamlit, Altair, or pandas
- [ ] The lockfile is regenerated with uv, not by hand
- [ ] pytest, ruff, mypy, and the web checks pass
- [ ] The PRD and design doc point at ADR 0006 for the window
