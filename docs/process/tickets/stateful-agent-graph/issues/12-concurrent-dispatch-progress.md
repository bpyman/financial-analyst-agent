# 12 — Concurrent dispatch and visible progress

**Spec:** 01 — Stateful analysis graph

**What to build:** A wide analysis that finishes in reasonable time and never looks hung. Eight quarters times four metrics is thirty-two independent cells; run them concurrently instead of one round trip after another. While a turn is working, the analyst sees progress rather than an indefinite spinner.

Concurrency must not change a single number. The same request produces the same values, provenance, and row order as the serial path, because task semantics stay in the existing deterministic tool functions and only their dispatch changes. Failure is isolated the same way: a provider error fails that cell with its typed reason and leaves the rest of the analysis and the **conversation thread** intact. Streaming exists here only to make a long turn legible, not as a product surface.

**Blocked by:** 11

**Status:** resolved

- [x] Independent cells in one analysis execute concurrently
- [x] A wide analysis returns the same values, provenance, and ordering as serial execution against the fixture runtime
- [x] A failed provider call fails one cell with its typed reason and does not fail the turn or the thread
- [x] Progress is visible while a long turn runs
- [x] Concurrency is bounded so a wide request cannot flood a provider

## Answer

`dispatch_compiled_tasks` runs independent compiled cells on a `ThreadPoolExecutor` capped at `DEFAULT_TASK_MAX_WORKERS` (8), preserving compile order when merging. Unexpected cell exceptions become typed partials so one failure cannot sink the turn or thread. `run_spec_turn` / `run_conversation_turn` accept `on_progress(done, total)` and optional `max_workers`; the Streamlit window drives `st.progress` from that callback instead of an indefinite spinner.
