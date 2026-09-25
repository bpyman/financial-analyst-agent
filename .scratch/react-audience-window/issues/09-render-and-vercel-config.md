# 09 — Render and Vercel deploy configuration

**What to build:** The deploy configuration is checked in, so a human only connects accounts.

- **Render blueprint:** free Docker web service in Virginia, health check path, public-demo environment (recorded runtime, `PUBLIC_DEMO=true`), and `API_PROXY_TOKEN` declared but not synced (set in the dashboard). It deploys only after GitHub CI passes; if the free tier lacks that setting, a CI job calls a deploy hook after all checks pass.
- **Vercel:** the project root is `web/`, with an ignored-build step so Python-only commits skip the web build. The proxy route's duration fits a long streamed turn. Environment variables: `API_ORIGIN` and `API_PROXY_TOKEN`.
- **Previews:** Vercel preview deploys call the production API.
- **Deploy notes:** rewritten for this setup, with the Streamlit Community Cloud notes marked legacy until cutover.

Spec: ADR 0006 ("Hosting").

**Blocked by:** 08

**Status:** ready-for-agent

- [ ] The blueprint validates against Render's published schema (checked against current docs)
- [ ] The Vercel settings are documented, and the ignored-build step is committed
- [ ] The deploy notes list every environment variable per service, and where it is set
