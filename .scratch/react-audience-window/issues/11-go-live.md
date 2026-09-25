# 11 — Go live on Render and Vercel

**What to build:** Blake runs the deploy wizard. The hosted `*.vercel.app` window serves the recorded runtime through the proxy, the Python origin refuses direct calls, and the browser check passes against the hosted URL.

Spec: ADR 0006 (cutover criteria).

**Blocked by:** 10

**Status:** ready-for-human

- [ ] The hosted URL answers all four guided stories
- [ ] A direct call to the Render URL without the token is refused
- [ ] The browser check passes with the base URL set to the hosted URL
- [ ] The hosted URL is recorded in this ticket's Answer
