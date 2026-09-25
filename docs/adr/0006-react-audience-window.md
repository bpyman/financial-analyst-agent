# A Next.js audience window over a thin HTTP seam, not Streamlit

The audience window moves from Streamlit to a React/Next.js app (`web/`) that talks to the Python core through a small FastAPI service (`financial_analyst_agent.api`). The API is a transport over seams that already exist: `run_conversation_turn` for a turn, `present_turn` for display records, `LocalThreadStore` for thread state, `SessionBudget` for public quotas, `runtime_for_kill_switch` for recorded versus live adapters. It adds no financial logic, and the browser receives the `Presentation` mapping as JSON — formatted strings, chart records, evidence items, traces — so the client never formats a number.

This supersedes PRD story 34 ("Streamlit to be the only audience window") and the audience-window ticket's out-of-scope line "Leaving Streamlit". It does not touch ADRs 0001–0005: membership, lookup gating, the quarterly fact module, clarify rules, and the stateful graph run underneath, unchanged.

## Locked

- **Presentation stays in Python.** `present_turn` is the only place a `Decimal` becomes a string. The client may choose chart axis tick formats from `chart_value_kind`, but amounts shown as text come from the server.
- **One turn endpoint, streamed.** `POST /api/threads/{thread_id}/turns` returns server-sent events: `progress` (`done`, `total` compiled cells), then exactly one `thread` (the whole thread view) or `error` (a public message — `ConfigurationError` and `SessionQuotaError` text, otherwise a generic failure).
- **One thread per browser, plus Start over.** The thread identifier is a server-minted UUID kept in `localStorage`; a reload resumes it until `THREAD_TTL_SECONDS` expires it. No thread list, no accounts (ADR 0005).
- **A thread is bound to one runtime, enforced by the conversation seam.** A thread picks the recorded or live runtime when it is created (`POST /api/threads {runtime}`); turns carry no runtime flag. `Runtime` carries which one it is, and `run_conversation_turn` refuses a turn whose runtime differs from the thread's with a typed error, so every caller — API, Streamlit until cutover, MCP, tests — gets the rule, not only the HTTP front door. Switching runtime in the window is Start over on the other runtime. When `PUBLIC_DEMO=true` and `DEMO_LIVE_SEC=false`, a request for a live thread is created recorded and the response says so; the window shows a disabled switch with a lock and "Live runtime is off on the public demo". (Streamlit let the switch flip mid-thread; that is the behaviour this replaces.)
- **Glossary words on screen.** The window labels the runtimes "Recorded" and "Live", and the recorded banner opens "Recorded runtime — captured SEC filings, not a live EDGAR pull." "Guided demo data" is retired.
- **Threads may be lost on restart.** The hosted thread store is a plain local disk, as it already was on Streamlit Community Cloud; threads also expire after `THREAD_TTL_SECONDS`. When a stored thread comes back empty, the window says so and starts fresh.
- **The API accepts only proxied calls.** The Vercel proxy sends a shared secret header; when `API_PROXY_TOKEN` is set, the API refuses requests without it, so the Python origin is not a second public entry point. Local runs leave it unset and need no secrets; the API logs a startup warning when `PUBLIC_DEMO=true` and the token is missing.
- **Clarify answers are messages.** A candidate button sends its catalog slug as the next analyst message, as before; only the last turn's candidates are live, and only while the thread holds a pending clarification.
- **Streamed progress stays.** Progress events are worth the proxy-buffering care: a ranked ten-company lookup otherwise looks hung.
- **Browser never calls Python directly.** A Next.js route handler proxies `/api/*` to `API_ORIGIN`, so there is no CORS surface and the Python host can move without a client rebuild.

## Hosting

Next.js on Vercel (`web/` as the project root). FastAPI in a container on Google Cloud Run's Starter Tier: free without a card, capped at one instance, request timeout configurable well past a long streamed turn. One instance is a requirement, not a limit: the file-backed thread store and the per-thread turn lock only work if every request for a thread reaches the same process. Cloud Run scales to zero, so the first visitor after idle waits for a cold start and the window says "Waking the analysis service…" rather than spinning. Vercel's Python functions were rejected because LangGraph and the thread store need a process that outlives one request. Render's free tier was the runner-up (same sleep behaviour, 0.1 CPU); Koyeb's free tier caps HTTP at 100s, which would cut long streams.

## Migration

Streamlit stays runnable alongside until cutover, then `app.py`, its tests, and the `streamlit`, `streamlit-shadcn-ui`, `altair`, and `pandas` dependencies are deleted in one follow-up. Two windows exist until then; both call the same seams, so neither can drift on numbers.

Cutover needs all three: the hosted Next.js URL serves the recorded runtime; a Playwright check in CI clicks each guided story and the compare-then-add-Apple walkthrough and finds the expected fact card, chart, table, or disclosure; and the README's portfolio images are re-captured from the new window by a Playwright script (`web/scripts/capture-portfolio.ts`) that drives the same walkthrough, so they can be regenerated whenever the window changes. The Playwright check replaces what `tests/test_app.py` guarded; there are no visual snapshot tests.

Scope is parity with the Streamlit window plus three display-only additions: copy buttons on identifiers, a turn counter, and a compact/full column switch on tables. CSV export and shareable thread links are out: a share link would reintroduce cross-visitor thread access.

## Considered Options

- **Keep Streamlit, restyle harder** — rejected: the rerun model fights multi-turn chat (turn-in-flight flags, pending-query session keys, full-page reruns on every click), and component styling is capped by what Streamlit exposes.
- **Next.js calls Python via Vercel Python functions** — rejected: no durable disk for threads, cold-start LangGraph imports, per-request process.
- **One container serving a static Next export from FastAPI** — rejected for now: one deploy is simpler, but it gives up Vercel previews and edge caching for the storefront. The API image stays independent so this remains a later option.
- **Port `presentation.py` to TypeScript** — rejected: two formatters would drift, and the numeral-lock story depends on one renderer.
- **Browser calls FastAPI with CORS** — rejected: exposes the Python origin and couples the client build to it.
- **Delete Streamlit in the same change** — rejected: the README's hosted link would point at nothing until the new host exists.

## Consequences

There are now two runtimes to deploy and a JSON contract between them (`web/lib/types.ts` mirrors `presentation.py`; `tests/test_api.py` pins the shape). A Python dataclass field rename is a client break unless both sides change together. SSE through a proxy needs buffering disabled end to end (`X-Accel-Buffering: no`, no compression on the stream). CI grows a Node job.
