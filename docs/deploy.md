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
and `web/scripts/ignore-build.sh`, plus the `deploy` job in `.github/workflows/ci.yml`.
A person only connects accounts, pastes one secret into both hosts, and stores
Vercel's deploy hook for CI. `tests/test_deploy_config.py` pins that configuration.

Neither host puts a commit on the public demo before CI passes on it (ADR 0006,
"Hosting"): Render waits for GitHub's checks, and Vercel production deploys only
when CI calls its deploy hook. See [production waits for CI](#production-waits-for-ci).

The Streamlit Community Cloud app is still the public URL until cutover (ticket 11
onward); its notes are [at the end](#legacy-streamlit-community-cloud).

## Going live: the wizard

```text
scripts/deploy_wizard.sh           # walk through going live, stage by stage
scripts/deploy_wizard.sh --check   # re-verify the saved deploy, no prompts
```

The account steps only a person can do are in `scripts/deploy_wizard.sh`. It runs on
macOS, Linux, or WSL and needs `bash` and `curl`. Python 3.8+ runs the guided-story
checks, and npm runs the browser check. `gh` is optional. Its nine stages:

1. **Before you start**: checks the tools, and that `master` has `render.yaml`,
   the `Dockerfile`, and `web/`. Both hosts build `master`, so the parity and deploy
   PRs must be merged first. If the Render CLI is installed, it runs
   `render blueprints validate`.
2. **Proxy token**: generates `API_PROXY_TOKEN` (`openssl rand -hex 32`). Re-runs
   keep the saved token, so Render and Vercel stay in step.
3. **Render**: New → Blueprint → the repo → `master`, and the token pasted into the
   field the Blueprint asks for. The wizard then waits for `/api/health`, checks that
   `/api/meta` without the token answers 401, and takes a guided story with the token.
4. **Render Auto-Deploy**: confirms that Settings → Auto-Deploy reads "After CI
   Checks Pass". If the free plan does not offer it, the wizard captures the
   deploy hook and sets the `RENDER_DEPLOY_HOOK_URL` secret with `gh`
   ([fallback](#fallback-deploy-hook-from-ci)). You then set
   `autoDeployTrigger: off` yourself.
5. **Vercel**: imports the repo with Root Directory `web`, then checks that the
   production `*.vercel.app` domain loads.
6. **Vercel Deploy Hook**: creates a Deploy Hook for `master` (Settings → Git →
   Deploy Hooks) and stores it as the `VERCEL_DEPLOY_HOOK_URL` secret with `gh`, or
   says where to paste it on github.com. It can call the hook once, which deploys
   `master` and proves the URL works. Its `curl` reads the URL from stdin, so the
   hook's key stays out of the process list.
7. **Vercel variables**: sets `API_ORIGIN` and `API_PROXY_TOKEN` (Sensitive) for
   Production and Preview, and redeploys. It then checks the health route and a
   guided story through the proxy.
8. **Proxy check**: runs every check again, as for `--check`.
9. **Browser check**: runs `PLAYWRIGHT_BASE_URL=<vercel url> npm run test:e2e`.

Values go to `.env.deploy`, which is gitignored: the token, both URLs, and the hook
URLs. They never go to `.env`, because the API reads `.env`, and a token
there would make the local API refuse the local window. A stage whose result already
checks out says so and moves on, so re-running after a partial run is safe.
`--check` exits 1 if any check fails. It does not look for the GitHub secrets;
`gh secret list` shows them.

Where the wizard names a dashboard control it could not confirm, it says what to
look for instead. See [what was checked](#what-was-checked-against-current-docs).

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
| GitHub Actions | `VERCEL_DEPLOY_HOOK_URL` | Vercel's Deploy Hook URL for `master` | Repository secret. Required: without it, merges to `master` never reach the hosted window. |
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
| `branch` | `master` | Deploys only `master`, the default branch. |
| `healthCheckPath` | `/api/health` | Open without the proxy token. |
| `numInstances` | `1` | Required: the file-backed thread store and per-thread turn lock need one process. |
| `autoDeployTrigger` | `checksPass` | Deploys a commit only after all its GitHub checks pass. |
| `buildFilter.paths` | `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock`, `src/**` | Commits that change only `web/`, docs, or tests do not rebuild the API. |

Create it once: Render dashboard → **New** → **Blueprint** → connect the GitHub repo →
pick `master`. Render reads `render.yaml`, asks for `API_PROXY_TOKEN`, and creates
`financial-analyst-api`. Later edits to `render.yaml` sync on push.
[The wizard](#going-live-the-wizard) walks through each click.

### Deploys wait for CI

With `autoDeployTrigger: checksPass`, Render waits for every GitHub check on the
commit: the `check`, `image`, `web`, and `deploy` jobs in `.github/workflows/ci.yml`,
plus any check another app posts (Vercel's, on pull request branches). Render counts a check as passed when it ends in
success, neutral, or skipped. A commit with **no** checks is never auto-deployed, and
neither is one where any check fails. A commit message containing `[skip render]`
skips the deploy.

### Fallback: deploy hook from CI

If `checksPass` is not offered for the free instance, CI can deploy instead:

1. Render → the service → **Settings** → **Deploy Hook**: copy the URL.
2. GitHub → **Settings** → **Secrets and variables** → **Actions**: add
   `RENDER_DEPLOY_HOOK_URL`.
3. In `render.yaml`, set `autoDeployTrigger: off`, so a commit is not deployed twice.

The `deploy` job in CI then POSTs to the hook on pushes to `master`, after `check`,
`image`, and `web` pass, before it calls Vercel's. Without the secret, it skips that
step.

## Vercel: the window

| Setting | Value | Where |
| --- | --- | --- |
| Framework preset | Next.js | Detected |
| Root Directory | `web` | Vercel dashboard → Project → **Settings** → **Build and Deployment** (asked when importing the repo) |
| Node.js | 22.x | `web/package.json` `engines`, matching `.nvmrc` |
| Ignored Build Step | `sh scripts/ignore-build.sh` | `web/vercel.json` `ignoreCommand`, which overrides the dashboard field |
| Git deploys of `master` | off | `web/vercel.json` `git.deploymentEnabled` `{"master": false}`. Production deploys through the Deploy Hook; other branches still get previews. |
| Deploy Hook | `ci-master`, branch `master` | Vercel dashboard → Project → **Settings** → **Git** → **Deploy Hooks**; its URL is the `VERCEL_DEPLOY_HOOK_URL` secret |
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
outside Vercel's shallow clone. Production builds come from the deploy hook, and users
report Vercel runs this step for them too. The comparison is still with `master`'s
last successful deployment, not the parent commit, so a `web/` change from a commit
whose CI failed ships with the next commit that passes. A hook call after
Python-only commits is skipped, and production keeps serving the same window. To
rebuild anyway, use **Redeploy** on the production deployment.

**Previews call the production API.** Set `API_ORIGIN` and `API_PROXY_TOKEN` for the
Preview environment too, with the same values. A preview then talks to the production
Render service. That is safe because every hosted thread runs the recorded runtime, and
the three-PR order lands API changes before the UI that depends on them. Previews
still build on push, before CI finishes; they sit behind Vercel's login (Deployment
Protection) and are not the public demo.

### Production waits for CI

`web/vercel.json` sets `"git": {"deploymentEnabled": {"master": false}}`, so a push to
`master` does not deploy the window. Instead, the `deploy` job in
`.github/workflows/ci.yml` runs on pushes to `master` once `check`, `image`, and `web`
pass (lint, types, tests, the image smoke test, and the Playwright check), and POSTs
to the `VERCEL_DEPLOY_HOOK_URL` secret. Vercel then builds `master` as a production
deployment. One job calls both hooks: Render's (only in the
[fallback](#fallback-deploy-hook-from-ci)) and then Vercel's, so one gate decides
when the API and then the window go out.

A deploy hook builds the branch's latest commit, not a given one. The job therefore
first checks that its commit is still the tip of `master`. If a newer commit has
landed, it calls no hook, and the newer commit's own run deploys once its checks
pass. A push that lands in the seconds between that check and the POST can still
ship before its own CI finishes; nothing on Vercel's side closes that gap without a
deploy token in CI.

The per-branch form matters. A plain `"deploymentEnabled": false` would also turn
off previews, and one user reports it blocked a production Deploy Hook as well.

Until `VERCEL_DEPLOY_HOOK_URL` is set, the job skips that step and merges to
`master` do not reach the hosted window. Stage 6 of the wizard sets it.

## Checking a deploy

```text
# the API, directly: health is open, everything else needs the token
curl -sS https://<render service>.onrender.com/api/health
curl -sS -o /dev/null -w "%{http_code}\n" https://<render service>.onrender.com/api/meta   # 401
SMOKE_PROXY_TOKEN=<token> python3 scripts/smoke_api_image.py --base-url https://<render service>.onrender.com

# through the window's proxy (no token: the proxy adds it)
curl -sS https://<project>.vercel.app/api/health
python3 scripts/smoke_api_image.py --base-url https://<project>.vercel.app

# the browser check against the hosted window
cd web && PLAYWRIGHT_BASE_URL=https://<project>.vercel.app npm run test:e2e
```

The smoke script reads the token from `SMOKE_PROXY_TOKEN`, so it stays out of the
process list; `--proxy-token <token>` also works and wins when both are given.

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
- **Vercel production gated on CI** (checked 25 September 2026, from search excerpts
  of vercel.com/docs/project-configuration/git-configuration and
  vercel.com/docs/deploy-hooks, plus public GitHub pull requests; vercel.com and
  community.vercel.com were blocked): `git.deploymentEnabled` takes `false` or an
  object of branch names or globs, and `{"<branch>": false}` turns off automatic
  deploys of that branch only. Deploy Hooks live under Settings → Git → Deploy
  Hooks, are bound to one branch, accept GET or POST with no payload, and build the
  branch's latest commit. `vercel deploy-hooks create <name> --ref <branch>` exists
  in Vercel CLI 60.0.1 (its `--help` was run). A September 2026 pull request
  (VNCHub/nossa-conta#19) reports that the object form `{"main": false}` kept a
  production Deploy Hook working while the global `false` blocked it. **Not
  verified**: that a hook build of the production branch becomes the production
  deployment (docs imply it but excerpts did not say so outright); whether the
  project import's first deploy runs despite the setting (the wizard handles both);
  and what `VERCEL_GIT_PREVIOUS_SHA` holds in a hook build. Forum reports say the
  Ignored Build Step runs for hook builds; `ignore-build.sh` builds whenever that
  variable is empty or unknown, so the worst case is an unneeded build. Vercel CLI's
  config validator accepts any `git` value, and the published schema
  (openapi.vercel.sh) was unreachable, so `git.deploymentEnabled` was **not**
  schema-validated.
- **Vercel**: from search excerpts of vercel.com docs and changelogs. Fluid compute on
  Hobby has a 300 s default and maximum duration. `"fluid": true` in `vercel.json` turns
  it on per deployment, and it is the default for new projects since 23 April 2025.
  `ignoreCommand` skips the build on exit 0 and builds on 1. `VERCEL_GIT_PREVIOUS_SHA`
  is set only when an Ignored Build Step is configured, and it is empty on a branch's
  first deployment. `web/vercel.json` passes the config validator in Vercel CLI 60.0.1,
  but that validator does not check `fluid`, `regions`, or `ignoreCommand` at the top
  level.
- **Dashboard steps in the wizard** come from search excerpts of Render's Blueprint
  and deploy docs and Vercel's monorepo, environment-variable, and
  deployment-protection docs, not from the dashboards themselves. These are: New →
  Blueprint → Connect → Deploy Blueprint; the `sync: false` prompt on first creation;
  Settings → Auto-Deploy and Deploy Hook; Import → Root Directory → Edit; Settings →
  Git → Deploy Hooks; Settings → Environment Variables with the Sensitive switch;
  Redeploy. Each step the wizard
  could not confirm also says where else to look.
- **Deployment Protection**: Standard Protection is on by default and puts deployment
  URLs behind a Vercel login. Sources disagree on whether the project's own
  `<name>.vercel.app` production domain stays public: a July 2025 changelog says
  Standard Protection now covers "all except production custom domains". If the
  window answers 401 or 403, the wizard names the Deployment Protection setting to
  change.

## Legacy: Streamlit Community Cloud

> Legacy until cutover (tickets 11–14). The public URL is still
> [financial-analyst-agent-project.streamlit.app](https://financial-analyst-agent-project.streamlit.app).
> At cutover the app is repointed at a `streamlit-redirect` branch that shows "This demo
> has moved", and `app.py` is deleted from `master`.

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
