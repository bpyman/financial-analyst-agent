# 03 — Only the window's proxy may call the API

**What to build:** On a hosted deploy the Python API answers only requests that came through the Next.js proxy. When `API_PROXY_TOKEN` is set, the API refuses any `/api/*` request, apart from the health check, that lacks the matching shared-secret header; the proxy adds that header from its own environment. With the token unset, as in local runs, nothing changes and no secrets are needed. When `PUBLIC_DEMO=true` and the token is missing, the API logs a warning at startup so a forgotten secret is visible in deploy logs.

Spec: ADR 0006 ("The API accepts only proxied calls").

**Blocked by:** None — can start immediately

**Status:** resolved

- [x] API tests: token set → requests without or with a wrong header get 401, and correct-header requests work; token unset → everything works; the health check works regardless
- [x] A startup warning appears for a public demo without a token
- [x] The proxy forwards the header only when the token is configured, and never exposes it to the browser
- [x] The comparison does not leak timing (constant-time)
- [x] `.env.example` and web env docs name the variable
- [x] pytest, ruff, and mypy pass

## Answer

Shipped 2026-09-25.

- `Settings.api_proxy_token` (`API_PROXY_TOKEN`, a `SecretStr` so it never shows in a settings repr). When set, `create_app` installs `ProxyTokenGuard`, a plain ASGI middleware (streamed turns pass through untouched) that answers `401 {"detail": "Not authorized."}` to any request except `/api/health` whose `X-Proxy-Token` header does not match. The compare is `hmac.compare_digest` on bytes. `/api/docs` and `/api/openapi.json` are behind the guard too.
- Token unset: no middleware, no behaviour change. `PUBLIC_DEMO=true` with no token logs a warning naming `API_PROXY_TOKEN` when the app is built.
- Web: `web/lib/proxy.ts` owns the header rules. `upstreamRequestHeaders` builds upstream headers from an allowlist (accept, content-type) and adds `x-proxy-token` only when `API_PROXY_TOKEN` is non-empty, so a browser-forged token is never forwarded. `clientResponseHeaders` returns only content-type, cache-control, and x-accel-buffering, so the secret cannot be echoed back. The route reads `process.env.API_PROXY_TOKEN` at request time (not `NEXT_PUBLIC_`, so not bundled).
- Docs: root `.env.example`, new `web/.env.example` (gitignore exception), `web/README.md` (replaces the create-next-app boilerplate), and ADR 0006 names the header.
- Checked end to end: with the token on both sides, direct `curl :8000/api/meta` gets 401, `/api/health` gets 200, and a thread plus a streamed turn work through the proxy.
