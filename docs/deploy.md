# Deploy notes

The hosted demo has two services (ADR 0006, "Hosting"):

```text
browser ──> Vercel: Next.js window (web/) ──/api/*──> Render: analysis API (Docker)
              proxy route adds X-Proxy-Token            refuses calls without it
```

The browser only talks to Vercel. The route handler `web/app/api/[...path]/route.ts`
forwards `/api/*` to `API_ORIGIN` and sends the shared secret. When the API has
`API_PROXY_TOKEN` set, it answers only proxied calls. `/api/health` stays open for
wake-up pings and Render's health check.

Everything a host reads is checked in: `render.yaml`, `Dockerfile`, `web/vercel.json`,
and `web/scripts/ignore-build.sh`. A person only connects accounts and pastes one
secret. `tests/test_deploy_config.py` pins that configuration.

The Streamlit Community Cloud app is still the public URL until cutover (ticket 11
onward); its notes are [at the end](#legacy-streamlit-community-cloud).

## Environment variables

| Service | Variable | Value | Where it is set |
| --- | --- | --- | --- |
| Render (API) | `APP_MODE` | `recorded` | `render.yaml` |
| Render (API) | `PUBLIC_DEMO` | `true` | `render.yaml` |
| Render (API) | `DEMO_LIVE_SEC` | `false` | `render.yaml` |
| Render (API) | `ALLOW_PUBLIC_OPENAI` | `false` | `render.yaml` |
| Render (API) | `ALLOW_PUBLIC_TAVILY` | `false` | `render.yaml` |
| Render (API) | `API_PROXY_TOKEN` | a random secret (for example `openssl rand -hex 32`) | Render dashboard. `render.yaml` declares it with `sync: false`, so the Blueprint prompts for it on first sync and never stores it. |
| Render (API) | `PORT` | `10000` by default | Render sets it. The image listens on `$PORT`. |
| Render (API) | `HOST`, `PYTHONUNBUFFERED` | `0.0.0.0`, `1` | `Dockerfile` |
| Vercel (window) | `API_ORIGIN` | `https://<render service>.onrender.com` (no trailing slash) | Vercel dashboard, Production **and** Preview |
| Vercel (window) | `API_PROXY_TOKEN` | the same secret as on Render | Vercel dashboard, Production **and** Preview, marked Sensitive |
| GitHub Actions | `RENDER_DEPLOY_HOOK_URL` | Render's deploy hook URL | Repository secret. Only for the [fallback](#fallback-deploy-hook-from-ci); leave unset otherwise. |

Neither Vercel variable is `NEXT_PUBLIC_`, so neither reaches the browser bundle.
Every other API setting keeps the default in `config.py` (thread TTL 7200 s, 25 turns
per thread). The recorded runtime needs no SEC, OpenAI, or Tavily keys; do not set them
on the public demo.

## Render: the analysis API

`render.yaml` is a Blueprint with one service:

| Field | Value | Why |
| --- | --- | --- |
| `type` / `runtime` | `web` / `docker` | Builds the repo's `Dockerfile` (context `.`). Both are fixed once the service exists. |
| `plan` | `free` | No card on file. 512 MB of RAM and a fraction of a CPU. It sleeps after 15 idle minutes and takes about a minute to wake. |
| `region` | `virginia` | Next to Vercel's `iad1` functions. Fixed once the service exists. |
| `branch` | `main` | Deploys only `main`. |
| `healthCheckPath` | `/api/health` | Open without the proxy token. |
| `numInstances` | `1` | Required: the file-backed thread store and per-thread turn lock need one process. |
| `autoDeployTrigger` | `checksPass` | Deploys a commit only after all its GitHub checks pass. |
| `buildFilter.paths` | `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock`, `src/**` | Commits that change only `web/`, docs, or tests do not rebuild the API. |

Create it once: Render dashboard → **New** → **Blueprint** → connect the GitHub repo →
pick `main`. Render reads `render.yaml`, asks for `API_PROXY_TOKEN`, and creates
`financial-analyst-api`. Later edits to `render.yaml` sync on push. The deploy wizard
(ticket 10) walks through each click.

### Deploys wait for CI

With `autoDeployTrigger: checksPass`, Render waits for every GitHub check on the
commit: the `check`, `image`, and `web` jobs in `.github/workflows/ci.yml`, plus any
check another app posts (Vercel's). Render counts a check as passed when it ends in
success, neutral, or skipped. A commit with **no** checks is never auto-deployed, and
neither is one where any check fails. A commit message containing `[skip render]`
skips the deploy.

### Fallback: deploy hook from CI

If `checksPass` is not offered for the free instance, CI can deploy instead:

1. Render → the service → **Settings** → **Deploy Hook**: copy the URL.
2. GitHub → **Settings** → **Secrets and variables** → **Actions**: add
   `RENDER_DEPLOY_HOOK_URL`.
3. In `render.yaml`, set `autoDeployTrigger: off`, so a commit is not deployed twice.

The `deploy-api` job in CI then POSTs to the hook on pushes to `main`, after `check`,
`image`, and `web` pass. Without the secret, the job does nothing.

## Vercel: the window

| Setting | Value | Where |
| --- | --- | --- |
| Framework preset | Next.js | Detected |
| Root Directory | `web` | Vercel dashboard → Project → **Settings** → **Build and Deployment** (asked when importing the repo) |
| Node.js | 22.x | `web/package.json` `engines`, matching `.nvmrc` |
| Ignored Build Step | `sh scripts/ignore-build.sh` | `web/vercel.json` `ignoreCommand`, which overrides the dashboard field |
| Fluid compute | on | `web/vercel.json` `"fluid": true`. It is already the default for new projects. |
| Function region | `iad1` (Washington, D.C.) | `web/vercel.json` `regions`. Hobby runs functions in one region, and `iad1` is its default. |
| Proxy duration | 300 s | `export const maxDuration = 300` in the proxy route. That is the Hobby maximum under Fluid compute, enough for a long streamed turn. |
| Environment variables | `API_ORIGIN`, `API_PROXY_TOKEN` | See [the table above](#environment-variables) |

Vercel reads `vercel.json` from the Root Directory, so it lives at `web/vercel.json`.

**Ignored build step.** Vercel runs `web/scripts/ignore-build.sh` from `web/` before
each build. It compares `HEAD` with `VERCEL_GIT_PREVIOUS_SHA`, the commit of the
branch's last successful deployment, and skips the build (exit 0) only when nothing
under `web/` changed. Python-only commits therefore do not rebuild the window. It
builds (exit 1) when that is unknown: a branch's first deployment, or a previous commit
outside Vercel's shallow clone.

**Previews call the production API.** Set `API_ORIGIN` and `API_PROXY_TOKEN` for the
Preview environment too, with the same values. A preview then talks to the production
Render service. That is safe because every hosted thread runs the recorded runtime, and
the three-PR order lands API changes before the UI that depends on them. Vercel does
not wait for GitHub CI; a preview or production build can go live before CI finishes on
the same commit.

## Checking a deploy

```text
# the API, directly: health is open, everything else needs the token
curl -sS https://<render service>.onrender.com/api/health
curl -sS -o /dev/null -w "%{http_code}\n" https://<render service>.onrender.com/api/meta   # 401
python3 scripts/smoke_api_image.py --base-url https://<render service>.onrender.com --proxy-token <token>

# through the window's proxy (no token: the proxy adds it)
curl -sS https://<project>.vercel.app/api/health
python3 scripts/smoke_api_image.py --base-url https://<project>.vercel.app

# the browser check against the hosted window
cd web && PLAYWRIGHT_BASE_URL=https://<project>.vercel.app npm run test:e2e
```

The first call after 15 idle minutes waits about a minute while Render wakes the
service. The window says "Waking the analysis service…" in the meantime.

## What was checked against current docs

This configuration was written on 25 September 2026. render.com and vercel.com were not
reachable from the build environment, so the fields were checked against these
sources:

- **Render Blueprint fields** (`runtime: docker`, `plan: free`, the `virginia` region,
  `healthCheckPath`, `numInstances`, `buildFilter.paths`, `envVars` with `sync: false`,
  and `autoDeployTrigger` with `commit` / `checksPass` / `off`, which replaces the
  deprecated `autoDeploy`) come from Render's own agent skills (render-oss/skills,
  `render-blueprints` and its field reference, MIT). They were cross-checked with
  search excerpts of render.com/docs/blueprint-spec. `tests/test_deploy_config.py`
  checks `render.yaml` against that field list. The official schema at
  `https://render.com/schema/render.yaml.json` was unreachable, so it was **not**
  validated against it. Run `render blueprints validate` (Render CLI 2.7+) or let the
  Blueprint sync report errors.
- **"After CI Checks Pass"** comes from search excerpts of render.com/docs/deploys and
  Render's changelog: success, neutral, and skipped count as passed, and a commit with
  zero checks is not deployed. No source said whether the free instance offers it,
  which is why the deploy hook fallback exists.
- **Render free-instance limits**: sleep after 15 idle minutes and about a minute to
  wake are from ADR 0006. The CPU share was not confirmed: ADR 0006 says 0.1 CPU, and
  one secondary reference (OpenAI's `render-deploy` skill) lists 0.5. Check Render's
  pricing page if it matters.
- **Vercel**: from search excerpts of vercel.com docs and changelogs. Fluid compute on
  Hobby has a 300 s default and maximum duration. `"fluid": true` in `vercel.json` turns
  it on per deployment, and it is the default for new projects since 23 April 2025.
  `ignoreCommand` skips the build on exit 0 and builds on 1. `VERCEL_GIT_PREVIOUS_SHA`
  is set only when an Ignored Build Step is configured, and it is empty on a branch's
  first deployment. `web/vercel.json` passes the config validator in Vercel CLI 60.0.1,
  but that validator does not check `fluid`, `regions`, or `ignoreCommand` at the top
  level.

## Legacy: Streamlit Community Cloud

> Legacy until cutover (tickets 11–14). The public URL is still
> [financial-analyst-agent-project.streamlit.app](https://financial-analyst-agent-project.streamlit.app).
> At cutover the app is repointed at a `streamlit-redirect` branch that shows "This demo
> has moved", and `app.py` is deleted from `main`.

The Streamlit window defaults to the recorded runtime, with isolated browser sessions,
thread expiry, and cached SEC responses. Community Cloud installs from
`requirements.txt` (exported from `uv.lock`). Free Community Cloud apps sleep when idle,
so the first visitor may have to wake the app.

1. Fork or connect `bpyman/financial-analyst-agent`.
2. Main file: `src/financial_analyst_agent/app.py`.
3. Copy `.streamlit/secrets.toml.example` into the app's secrets. Keep
   `APP_MODE=recorded` and `PUBLIC_DEMO=true`.
4. Check that the first guided story (`Verify a quarterly fact`) returns a table.

Keep the boolean flags quoted in the secrets template. Streamlit exports top-level
strings and numbers to environment variables, but not TOML booleans, and the app's
settings read those environment variables.

Local smoke:

```text
uv run python -m pytest tests/test_demo_smoke.py -q
uv run python -m streamlit run src/financial_analyst_agent/app.py
```
