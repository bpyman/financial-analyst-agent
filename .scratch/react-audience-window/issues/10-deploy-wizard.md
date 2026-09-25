# 10 — A wizard walks the human through going live

**What to build:** An interactive terminal wizard for the steps only a human can do:
- generate a proxy token;
- create the Render service from the blueprint and paste the token;
- create the Vercel project with the root directory set to `web/`;
- set `API_ORIGIN` and the token on Vercel;
- confirm the health check through the Vercel URL;
- run the browser check against the hosted URL.

The wizard verifies each step where it can, and can be re-run safely.

Spec: ADR 0006 ("Hosting"), the wizard skill.

**Blocked by:** 09

**Status:** ready-for-agent

- [ ] The wizard script is checked in and linked from the deploy notes
- [ ] Every step says exactly where in each dashboard to click and what to paste
- [ ] Re-running after a partial run skips completed steps or re-verifies them
