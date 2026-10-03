# 08 — Read follow-up wording in one place, and share the conversation test helpers

**What to build:** "what about / how about / same for" is read twice: by the shared edit reading (`spec_turn._INSTEAD_EDIT`, ADR 0010) and again by the rules planner's `_SWAP_WORDING`. ADR 0011 puts such fixes in the shared layers; remove the rules planner's copy once the shared reading covers what it does (industry swaps after a ranking stay with the planner).

The conversation test helpers (`_thread`, `_column`, `_tickers`) are copied across `tests/test_planner_conversations.py`, `tests/test_user_testing_round3.py`, `tests/test_user_testing_round4.py` and `tests/test_new_figures.py`; move them to one module under `tests/`.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: duplicated code).

Spec: ADR 0010, ADR 0011.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
