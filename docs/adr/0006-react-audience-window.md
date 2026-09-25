# A Next.js audience window over a thin HTTP seam, not Streamlit

The audience window moves from Streamlit to a React/Next.js app (`web/`) that talks to the Python core through a small FastAPI service (`financial_analyst_agent.api`). The API is a transport over seams that already exist: `run_conversation_turn` for a turn, `present_turn` for display records, `LocalThreadStore` for thread state, `SessionBudget` for public quotas, `runtime_for_kill_switch` for recorded versus live adapters. It adds no financial logic, and the browser receives the `Presentation` mapping as JSON — formatted strings, chart records, evidence items, traces — so the client never formats a number.

This supersedes PRD story 34 ("Streamlit to be the only audience window") and the audience-window ticket's out-of-scope line "Leaving Streamlit". It does not touch ADRs 0001–0005: membership, lookup gating, the quarterly fact module, clarify rules, and the stateful graph run underneath, unchanged.

## Locked

- **Presentation stays in Python.** `present_turn` is the only place a `Decimal` becomes a string. The client may choose chart axis tick formats from `chart_value_kind`, but amounts shown as text come from the server.
- **One turn endpoint, streamed.** `POST /api/threads/{thread_id}/turns` returns server-sent events: `progress` (`done`, `total` compiled cells), then exactly one `thread` (the whole thread view) or `error` (a public message — `ConfigurationError` and `SessionQuotaError` text, otherwise a generic failure).
- **One thread per browser, plus Start over.** The thread identifier is a server-minted UUID kept in `localStorage`; a reload resumes it until `THREAD_TTL_SECONDS` expires it. No thread list, no accounts (ADR 0005).
- **Recorded mode is a thread property.** Switching between recorded and live data starts a new thread, so recorded and live evidence never mix on one thread. When `PUBLIC_DEMO=true` and `DEMO_LIVE_SEC=false`, recorded mode is forced and the switch is locked.
- **Clarify answers are messages.** A candidate button sends its catalog slug as the next analyst message, as before; only the last turn's candidates are live, and only while the thread holds a pending clarification.
- **Browser never calls Python directly.** A Next.js route handler proxies `/api/*` to `API_ORIGIN`, so there is no CORS surface and the Python host can move without a client rebuild.

## Hosting

Next.js on Vercel (`web/` as the project root). FastAPI in a long-lived container (`Dockerfile`, `render.yaml`) because LangGraph and the file-backed thread store need a process and a disk that outlive one request. Vercel's Python functions were rejected for the same reason.

## Migration

Streamlit stays runnable alongside until the new hosted demo is live, then `app.py`, its tests, and the `streamlit`, `streamlit-shadcn-ui`, `altair`, and `pandas` dependencies are deleted in one follow-up. Two windows exist during that window of time; both call the same seams, so neither can drift on numbers.

## Considered Options

- **Keep Streamlit, restyle harder** — rejected: the rerun model fights multi-turn chat (turn-in-flight flags, pending-query session keys, full-page reruns on every click), and component styling is capped by what Streamlit exposes.
- **Next.js calls Python via Vercel Python functions** — rejected: no durable disk for threads, cold-start LangGraph imports, per-request process.
- **One container serving a static Next export from FastAPI** — rejected for now: one deploy is simpler, but it gives up Vercel previews and edge caching for the storefront. The API image stays independent so this remains a later option.
- **Port `presentation.py` to TypeScript** — rejected: two formatters would drift, and the numeral-lock story depends on one renderer.
- **Browser calls FastAPI with CORS** — rejected: exposes the Python origin and couples the client build to it.
- **Delete Streamlit in the same change** — rejected: the README's hosted link would point at nothing until the new host exists.

## Consequences

There are now two runtimes to deploy and a JSON contract between them (`web/lib/types.ts` mirrors `presentation.py`; `tests/test_api.py` pins the shape). A Python dataclass field rename is a client break unless both sides change together. SSE through a proxy needs buffering disabled end to end (`X-Accel-Buffering: no`, no compression on the stream). CI grows a Node job.
