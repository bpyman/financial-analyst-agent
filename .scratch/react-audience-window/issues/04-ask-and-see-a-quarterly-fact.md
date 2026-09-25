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

**Status:** ready-for-agent

- [ ] Running the API in the recorded runtime and the web app locally, "Verify a quarterly fact" shows the Microsoft pretax-income fact card with traces and evidence
- [ ] Reload keeps the thread; Start over clears it; switching runtime starts a new thread; the locked switch shows its tooltip
- [ ] A refused question (unknown metric) shows the refusal message; an API outage shows a friendly error
- [ ] Web lint, typecheck, unit tests, and production build pass
- [ ] The README says how to run the API and the web app locally
