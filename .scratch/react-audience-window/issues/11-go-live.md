# 11 — Go live on Render and Vercel

**What to build:** Blake runs the deploy wizard. The hosted `*.vercel.app` window serves the recorded runtime through the proxy, the Python origin refuses direct calls, and the browser check passes against the hosted URL.

Spec: ADR 0006 (cutover criteria).

**Blocked by:** 10

**Status:** resolved

- [x] The hosted URL answers all four guided stories
- [x] A direct call to the Render URL without the token is refused
- [x] The browser check passes with the base URL set to the hosted URL
- [x] The hosted URL is recorded in this ticket's Answer

## Answer

The hosted window is **https://financial-analyst-agent-ten.vercel.app** (live 25 September 2026). README and the release notes link it.

- **Render:** a free Docker web service in Virginia, `financial-analyst-api` at `https://financial-analyst-api-6yd0.onrender.com`, created through Render's REST API with the Blueprint's settings (`render.yaml` stays the record). `autoDeployTrigger: checksPass` was accepted on the free plan. `API_PROXY_TOKEN` is set, and the recorded runtime is locked (`PUBLIC_DEMO` on, `DEMO_LIVE_SEC` off).
- **Vercel:** Hobby project `financial-analyst-agent`, root `web`, Node 22, with `API_ORIGIN` and `API_PROXY_TOKEN` (sensitive) for production and preview. Automatic `master` deploys are off; the Deploy Hook "master after CI" built the first production deployment, and the `VERCEL_DEPLOY_HOOK_URL` repository secret lets CI's `deploy` job call it. The production domain is public under the default Deployment Protection.
- **Direct calls refused:** the Render URL answers 401 without the proxy token; `/api/health` stays open.
- **Guided stories:** all four answered through the hosted proxy on fresh recorded threads (SSE `progress` … `thread`): the MSFT fact card ($32.01 B), the four-quarter trend with chart and table, rank then inspect with chart and table, and the 10-Q change with two disclosures.
- **Browser check:** `PLAYWRIGHT_BASE_URL=<hosted URL> npx playwright test` passes 11/11. It first failed one test, which expected `locked: false`, true only of the local run; the test now expects the hosted demo to be locked. The run went through a local relay because the build sandbox's egress proxy breaks Chromium's own connections; the relay only forwards requests.
- **Old Streamlit URL:** repointed at the `streamlit-redirect` branch the same day (see `docs/deploy.md`).

`docs/deploy.md` → "Verified at go-live" records what going live settled.
