# 04 — Ask the new window a question and see a quarterly fact

**What to build:** The tracer bullet for the Next.js window. An analyst opens the app, sees the landing page, clicks "Verify a quarterly fact" or types a question, watches progress stream in, and gets the answer. The answer shows:
- a **fact card**: hero amount, metric, company and ticker, period, form, accession and concept, and an Open filing link;
- the **evidence inspector**: exact source, raw decimal amount, CIK, selection rule;
- **How this answer was fetched**: tool traces with request and result;
- **banners**, and **refusal or error messages**.

The shell around the answer:
- **Header:** runtime switch labelled "Recorded" / "Live", locked with a lock icon and tooltip when the deploy forces the recorded runtime; theme toggle; Start over.
- **Status line:** the snapshot banner (amber when stale), the runtime banner, active-analysis chips, and a turn counter ("3 of 25 turns").
- **Landing page:** guided stories, "What you can ask", and supported metrics.
- **Composer:** stays at the bottom; Enter sends.

Behaviour:
- **Thread persistence.** The thread id is kept in local storage, so a reload returns to the same thread. An expired or empty thread says so quietly and starts fresh.
- **Start over** clears the thread and starts a new one on the same runtime. Switching runtime is Start over on the other runtime.
- **Wake on visit.** The landing page pings the health check on load, and a turn with no progress after about 3 seconds says "Waking the analysis service…".
- **One turn at a time.** Sending is disabled while a turn runs.
- **Copy buttons** on accession number and CIK.

Visual direction: dark financial-terminal feel by default, with a light theme and a system option; tabular numerals; works down to phone width. The window adds no financial logic: every amount shown as text comes from the server.

Spec: ADR 0006.

**Blocked by:** 02

**Status:** resolved

- [x] Running the API in the recorded runtime and the web app locally, "Verify a quarterly fact" shows the Microsoft pretax-income fact card with traces and evidence
- [x] Reload keeps the thread; Start over clears it; switching runtime starts a new thread; the locked switch shows its tooltip
- [x] A refused question (unknown metric) shows the refusal message; an API outage shows a friendly error
- [x] Web lint, typecheck, unit tests, and production build pass
- [x] The README says how to run the API and the web app locally

## Answer

Shipped 2026-09-25.

- **Window:** `web/app/page.tsx` renders `components/analyst-window.tsx`, which owns meta, the thread view, and the turn. Around it: `header.tsx` (Recorded / Live switch with a lock icon and a tooltip when locked; System / Light / Dark theme control; Start over), `status-line.tsx` (runtime banner, snapshot banner in amber when stale, active-analysis chips, "N of M turns"), `landing.tsx` (guided stories, "What you can ask", supported metrics), `composer.tsx` (pinned to the bottom, Enter sends, Shift+Enter adds a line, send blocked while a turn runs), `thread.tsx` (question bubbles, progress, a failed turn with Try again), and `answer.tsx` (fact card, refusal/message callout, banners, evidence inspector, "How this answer was fetched" traces with Request and Result). `copy-button.tsx` copies accession numbers and CIKs.
- **Seams, unit-tested in vitest:** `lib/browser-thread.ts` holds the one-thread-per-browser rules. `resumeThread` resumes the stored id, and forgets a thread that comes back unknown or empty (`runtime: null`, no turns) with a quiet notice; an outage keeps the id. `startThread` deletes the old thread (best effort), creates one on the requested runtime, and stores its id; Start over and a runtime switch both call it. `lib/turn-state.ts` is the turn reducer (one turn at a time; "Waking the analysis service…" only while nothing has come back after `WAKE_AFTER_MS` = 3 s; failure keeps the question and the public message), plus the progress and turn-counter labels.
- **Wake on visit:** `pingHealth()` runs on load. The landing page also says the service is waking if the storefront copy takes more than 3 s.
- **API:** `/api/meta` `runtime_copy` gains `locked` (the locked-switch tooltip, `LIVE_RUNTIME_LOCKED_NOTICE`). `RECORDED_BANNER` now opens "Recorded runtime — captured SEC filings, not a live EDGAR pull." per ADR 0006; "Guided demo data" is gone. `getMeta()` takes an optional `recorded` flag, and the window asks for the snapshot banner of the runtime in use.
- **No client formatting:** amounts, periods, labels, and the refusal text are all server strings. The fact card's hero amount uses the sans face with tabular figures (`.figure`); identifiers use Geist Mono.
- **Checked by hand** in Chromium against `APP_MODE=recorded uv run serve-api` and `npm start`, at 1440px and 390px, dark and light: the "Verify a quarterly fact" story shows the MSFT pretax-income card ($32.01 B, 10-Q, 0001193125-26-191507, PretaxIncomeLoss) with evidence and traces. A reload keeps the thread id; Start over and the Live switch each mint a new thread, and the switched one is bound `live`. A locked meta shows the tooltip. An unknown metric (EBITDA) shows the refusal. A 502 from the proxy shows "The analysis service is unreachable. Please try again shortly." with Try again. A made-up stored id shows the expired notice.
- The root README and `web/README.md` say how to run the API and the web app locally.
