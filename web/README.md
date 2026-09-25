# Audience window

The Next.js window for the financial analyst agent (ADR 0006,
`docs/adr/0006-react-audience-window.md`). The browser only ever calls this
app's `/api/*`; the route handler in `app/api/[...path]/route.ts` proxies each
call to the Python API.

## Run locally

```bash
# repo root: the API on port 8000, recorded runtime
APP_MODE=recorded uv run serve-api

# web/
npm install
npm run dev   # http://localhost:3000
```

No secrets are needed locally.

## Environment

Both variables are read by the proxy route on the server; neither is
`NEXT_PUBLIC_`, so neither is bundled for the browser. See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_ORIGIN` | `http://127.0.0.1:8000` | Base URL of the Python API. |
| `API_PROXY_TOKEN` | unset | Shared secret sent upstream as `X-Proxy-Token`. Set it to the API's `API_PROXY_TOKEN` on a hosted deploy; the API then refuses any call but `/api/health` that did not come through this proxy. Unset, no header is sent. |

## Checks

```bash
npm run lint && npx tsc --noEmit && npx vitest run && npm run build
```
