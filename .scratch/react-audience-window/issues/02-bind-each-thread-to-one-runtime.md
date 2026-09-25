# 02 — Bind each conversation thread to one runtime

**What to build:** A conversation thread is started on the recorded runtime or the live runtime and never takes a turn on the other one, so recorded and live evidence never mix on a thread.

- **Rule in the seam.** The conversation seam records a thread's runtime on its first turn, or when the thread is created, and refuses a turn on the other runtime with a typed error. Every caller gets the rule, not only the HTTP front door. A thread saved before binding existed binds to whichever runtime its next turn uses.
- **HTTP API.** A thread picks its runtime when it is created, and turn requests no longer carry a runtime flag. On a locked public demo (`PUBLIC_DEMO=true`, `DEMO_LIVE_SEC=false`), a request for a live thread is created recorded and the response says so. The thread view reports the thread's runtime. A mismatched turn surfaces as a public error, never a stack trace.
- **Streamlit, until cutover.** Flipping the switch does Start over on the other runtime instead of clearing the screen and keeping the thread.

Spec: ADR 0006 ("A thread is bound to one runtime, enforced by the conversation seam"), `CONTEXT.md` (Conversation thread).

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Seam-level tests: first turn binds; mismatched turn refused with the typed error and nothing persisted; an unbound saved thread binds on its next turn
- [ ] API tests: create a recorded thread and a live thread; turns follow the thread's runtime; the locked demo coerces live to recorded and reports it; a mismatch streams a public `error` event
- [ ] Streamlit test: flipping the switch starts a new thread on the other runtime
- [ ] The web client's types and API client follow the new create-thread shape
- [ ] pytest, ruff, and mypy pass
