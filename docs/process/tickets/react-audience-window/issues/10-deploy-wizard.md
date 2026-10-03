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

**Status:** resolved

- [x] The wizard script is checked in and linked from the deploy notes
- [x] Every step says exactly where in each dashboard to click and what to paste
- [x] Re-running after a partial run skips completed steps or re-verifies them

## Answer

`scripts/deploy_wizard.sh` is the go-live wizard. It is built from the wizard skill's
template, with the library above the STAGES marker unchanged, and is linked from
`docs/deploy.md` ("Going live: the wizard") and the README. It has eight stages:

1. Before you start: checks for curl, Python 3.8+, npm, and gh, and that `origin/master`
   has `render.yaml`, the `Dockerfile`, and `web/`. That check fails today, because PRs 1
   and 2 are not merged yet. If the Render CLI is installed, it runs
   `render blueprints validate`.
2. Proxy token: `openssl rand -hex 32`, falling back to Python, then `/dev/urandom`. Re-runs keep it.
3. Render: New → Blueprint → Connect → `master`. The token goes on the clipboard to paste
   into the `sync: false` field. Then it asks for the service URL, waits up to 20 minutes
   for the first build, checks that `/api/meta` without the token answers 401, and takes
   the "Verify a quarterly fact" guided story with the token (`scripts/smoke_api_image.py`).
4. Render Auto-Deploy: you confirm that it reads "After CI Checks Pass". If the free
   plan lacks it, the wizard captures the deploy hook and sets `RENDER_DEPLOY_HOOK_URL`
   with `gh`, or says where to paste it on github.com. The `autoDeployTrigger: off`
   change to `render.yaml` and its test goes on the closing to-do list.
5. Vercel: `vercel.com/new` → Import → Root Directory Edit → `web` → Deploy. It then
   asks for the short production domain and checks that the page answers 200. A 401
   or 403 gets a Deployment Protection hint.
6. Vercel variables: `API_ORIGIN` and `API_PROXY_TOKEN` (Sensitive) for Production and
   Preview, then Redeploy. It checks the health route and the guided story through the proxy.
7. Proxy check: every check again, which is the cutover evidence.
8. Browser check: `npm ci` if needed, then `npx playwright install chromium` and
   `PLAYWRIGHT_BASE_URL=<vercel url> npm run test:e2e`.

Values go to `.env.deploy` (newly gitignored), never `.env`, because the API reads `.env`.
Each stage re-checks its result first and says "nothing to do here" when it passes.
`--check` re-runs every check against the saved deploy without prompts and exits 1 on a
failure. `tests/test_deploy_wizard.py` runs `--help` and `--check` against in-process APIs
standing in for Render (with the token) and the Vercel proxy (without it).

Dashboard steps come from search excerpts of Render's and Vercel's docs, because the
container cannot reach either site. Each step the wizard could not confirm says what to
look for instead. One open question: whether Standard Deployment Protection gates
`<name>.vercel.app`. The July 2025 changelog says "all except production custom domains".
