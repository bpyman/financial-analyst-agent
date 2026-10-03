# 08 — Read follow-up wording in one place

**What to build:** "what about / how about / same for" is read twice: by the shared edit reading (`spec_turn._INSTEAD_EDIT`, ADR 0010) and again by the rules planner's `_SWAP_WORDING`. ADR 0011 puts such fixes in the shared layers; remove the rules planner's copy once the shared reading covers what it does (industry swaps after a ranking stay with the planner).

The conversation test helpers that were copied across four test files now live in `tests/conversation_replay.py`; only the wording half is open.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: duplicated code).

Spec: ADR 0010, ADR 0011.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
