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

**Status:** ready-for-agent

- [ ] The Playwright suite passes locally against the recorded runtime
- [ ] The CI workflow has a web job that installs from the lockfile and runs all checks; Python checks unchanged
- [ ] Selectors use roles and labels, not CSS internals
- [ ] The suite can target another base URL through an environment variable
