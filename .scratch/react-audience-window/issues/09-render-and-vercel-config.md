# 09 — Render and Vercel deploy configuration

**What to build:** The deploy configuration is checked in, so a human only connects accounts.

- **Render blueprint:** free Docker web service in Virginia, health check path, public-demo environment (recorded runtime, `PUBLIC_DEMO=true`), and `API_PROXY_TOKEN` declared but not synced (set in the dashboard). It deploys only after GitHub CI passes; if the free tier lacks that setting, a CI job calls a deploy hook after all checks pass.
- **Vercel:** the project root is `web/`, with an ignored-build step so Python-only commits skip the web build. The proxy route's duration fits a long streamed turn. Environment variables: `API_ORIGIN` and `API_PROXY_TOKEN`.
- **Previews:** Vercel preview deploys call the production API.
- **Deploy notes:** rewritten for this setup, with the Streamlit Community Cloud notes marked legacy until cutover.

Spec: ADR 0006 ("Hosting").

**Blocked by:** 08

**Status:** resolved

- [x] The blueprint validates against Render's published schema (checked against current docs). Checked against Render's own Blueprint field reference; the JSON schema URL was unreachable, see Answer
- [x] The Vercel settings are documented, and the ignored-build step is committed
- [x] The deploy notes list every environment variable per service, and where it is set

## Answer

Shipped on 2026-09-25:

- `render.yaml` defines one service, `financial-analyst-api`: `type: web`, `runtime: docker`, `plan: free`, `region: virginia`, `branch: main`, `dockerfilePath: ./Dockerfile`, `dockerContext: .`, `healthCheckPath: /api/health`, and `numInstances: 1`. `autoDeployTrigger: checksPass` makes Render wait for every GitHub check. `buildFilter.paths` lists only what the image is built from, so web-only commits do not rebuild the API. The env sets `APP_MODE=recorded`, `PUBLIC_DEMO=true`, `DEMO_LIVE_SEC=false`, and `ALLOW_PUBLIC_OPENAI` / `ALLOW_PUBLIC_TAVILY=false`. `API_PROXY_TOKEN` is `sync: false`.
- Fallback: a `deploy-api` CI job on pushes to `main` needs `check`, `image`, and `web`, then POSTs to `RENDER_DEPLOY_HOOK_URL`. It does nothing until that secret exists. With the secret set, `autoDeployTrigger` must be `off`.
- `web/vercel.json` sets `ignoreCommand: sh scripts/ignore-build.sh`, `fluid: true`, and `regions: ["iad1"]`. The proxy route keeps `maxDuration = 300`, the Hobby maximum under Fluid compute. `web/scripts/ignore-build.sh` skips the build only when nothing under `web/` changed since `VERCEL_GIT_PREVIOUS_SHA`; when that is unknown, it builds.
- Previews use the same `API_ORIGIN` and `API_PROXY_TOKEN` as production, set for both environments in Vercel.
- `docs/deploy.md` is rewritten. It has a table of every environment variable per service and where it is set, the Render and Vercel settings, a deploy check, a section on what was verified against current docs, and the Streamlit Community Cloud notes marked legacy.
- `tests/test_deploy_config.py` does five things. It checks `render.yaml` against Render's field list and pins the values above. It runs the API with the Blueprint's env plus a token, so the guided story passes with the token and gets 401 without it. It pins the CI fallback job and `vercel.json`, checks that the route's `maxDuration` is 300, and runs the ignore script against a throwaway git repo in four cases.

Not verified: render.com and vercel.com could not be reached. The Blueprint was checked against Render's `render-oss/skills` field reference and search excerpts of the docs, not against `https://render.com/schema/render.yaml.json`. It is still unconfirmed whether the free instance offers "After CI Checks Pass", which is why the fallback exists. Ticket 10's wizard should run `render blueprints validate`, or read the Blueprint sync result, and confirm the auto-deploy setting in the dashboard.
