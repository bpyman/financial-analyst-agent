# 02 — Bind each conversation thread to one runtime

**What to build:** A conversation thread is started on the recorded runtime or the live runtime and never takes a turn on the other one, so recorded and live evidence never mix on a thread.

- **Rule in the seam.** The conversation seam records a thread's runtime on its first turn, or when the thread is created, and refuses a turn on the other runtime with a typed error. Every caller gets the rule, not only the HTTP front door. A thread saved before binding existed binds to whichever runtime its next turn uses.
- **HTTP API.** A thread picks its runtime when it is created, and turn requests no longer carry a runtime flag. On a locked public demo (`PUBLIC_DEMO=true`, `DEMO_LIVE_SEC=false`), a request for a live thread is created recorded and the response says so. The thread view reports the thread's runtime. A mismatched turn surfaces as a public error, never a stack trace.
- **Streamlit, until cutover.** Flipping the switch does Start over on the other runtime instead of clearing the screen and keeping the thread.

Spec: ADR 0006 ("A thread is bound to one runtime, enforced by the conversation seam"), `CONTEXT.md` (Conversation thread).

**Blocked by:** 01

**Status:** resolved

- [x] Seam-level tests: first turn binds; mismatched turn refused with the typed error and nothing persisted; an unbound saved thread binds on its next turn
- [x] API tests: create a recorded thread and a live thread; turns follow the thread's runtime; the locked demo coerces live to recorded and reports it; a mismatch streams a public `error` event
- [x] Streamlit test: flipping the switch starts a new thread on the other runtime
- [x] The web client's types and API client follow the new create-thread shape
- [x] pytest, ruff, and mypy pass

## Answer

Shipped 2026-09-25.

- **Seam.** `ThreadState.runtime` (`RuntimeKind | None`) records the binding. `start_thread(thread_id, kind, store=)` creates an empty bound thread; otherwise the first `run_conversation_turn` binds it to `runtime.kind`. A turn on the other runtime raises `RuntimeMismatchError` (code `runtime_mismatch`, details `{thread, turn}`) before any provider call, evidence write, or save. A checkpoint with no `runtime` key loads as unbound and binds on its next turn. Tests: `tests/unit/test_thread_runtime.py`.
- **Runtime choice.** `resolve_runtime_kind(kind, settings)` holds the locked-demo coercion; `default_runtime_kind(settings)` is `APP_MODE` after the lock. `runtime_for` and `build_runtime` use them.
- **HTTP API.** `POST /api/threads` takes an optional `{runtime}` (default: `APP_MODE`) and returns `{thread_id, runtime, notice}`; `notice` is "Live runtime is off on the public demo" when a locked demo served recorded instead of live. `TurnRequest` is `{message}` only and forbids extra keys, so an old `recorded` flag is a 422. Turns use the thread's bound runtime (deployment default for an unbound or missing thread). The thread view carries `runtime` (`null` when unbound). A mismatch streams a public `error` event and does not count against the turn quota. `public_error_message` passes `RuntimeMismatchError` text through.
- **Streamlit.** When the current thread is bound to the other runtime, flipping the switch does Start over (clears the old thread, mints a new one). `history_recorded` session state is gone.
- **Web client.** `types.ts` gains `RuntimeKind`, `CreatedThread`, and `ThreadView.runtime`; `createThread(runtime?)` returns `CreatedThread`; `runTurn` no longer takes `recorded`.
- `/api/meta` still reports `recorded: {default, locked}` and takes `?recorded=` for the snapshot banner; the window tickets can use it for the switch default and lock.
