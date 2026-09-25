# 03 — Only the window's proxy may call the API

**What to build:** On a hosted deploy the Python API answers only requests that came through the Next.js proxy. When `API_PROXY_TOKEN` is set, the API refuses any `/api/*` request, apart from the health check, that lacks the matching shared-secret header; the proxy adds that header from its own environment. With the token unset, as in local runs, nothing changes and no secrets are needed. When `PUBLIC_DEMO=true` and the token is missing, the API logs a warning at startup so a forgotten secret is visible in deploy logs.

Spec: ADR 0006 ("The API accepts only proxied calls").

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] API tests: token set → requests without or with a wrong header get 401, and correct-header requests work; token unset → everything works; the health check works regardless
- [ ] A startup warning appears for a public demo without a token
- [ ] The proxy forwards the header only when the token is configured, and never exposes it to the browser
- [ ] The comparison does not leak timing (constant-time)
- [ ] `.env.example` and web env docs name the variable
- [ ] pytest, ruff, and mypy pass
