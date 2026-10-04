# 08 — Read follow-up wording in one place

**What to build:** "what about / how about / same for" is read twice: by the shared edit reading (`request_wording._INSTEAD_EDIT`, ADR 0010) and again by the rules planner's `_SWAP_WORDING`. ADR 0011 puts such fixes in the shared layers; remove the rules planner's copy once the shared reading covers what it does (industry swaps after a ranking stay with the planner).

The conversation test helpers that were copied across four test files now live in `tests/conversation_replay.py`; only the wording half is open.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: duplicated code).

Spec: ADR 0010, ADR 0011.

**Blocked by:** None — can start immediately

**Status:** done

## Answer

The swap cues ("what about", "how about", "same for", "just", "only", "instead", "now", "ok", "by") are read once, by `request_wording.asks_to_swap`. The shared edit reading now swaps a metric for both planners (`_metric_swap`): a follow-up that names a metric and no company puts it in place of the metrics on screen, unless it adds ("now add net income", "net income too") or says "their"/"its". The rules planner's copy (`_SWAP_WORDING`) is gone: its metric branch proposes the metric and leaves the swap to the shared reading, and its company branch calls `asks_to_swap`. Industry swaps after a ranking stay with the planner. Before the change, the LLM planner (the public demo's) was checked on the recorded data: "what about net income", "how about operating margin" and "same for net income" added the metric beside revenue, while the rules planner swapped it, so the rules-based tests hid the gap. After it, all three swap on the LLM path too. The rules planner scores the same on all 219 evaluation cases. ADR 0010 says so.
