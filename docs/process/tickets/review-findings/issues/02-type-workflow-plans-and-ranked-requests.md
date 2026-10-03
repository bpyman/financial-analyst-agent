# 02 — Type workflow plans and ranked requests

**What to build:** Workflow plans are one frozen type instead of `SimpleNamespace` objects read with `getattr`. `graph/spec_turn.execute_compiled_task`, `DemoCompleter`/`rules_planner`, and the turn workflows in `turn.py` (`plan.company`, `getattr(plan, "report_date", None)`, `getattr(plan, "section", ...)` in `filing_change`) all build or read the same handful of fields, so a typo in a field name silently becomes `None` today.

In the same pass, replace `SpecPatch.ranked_request` / `SpecDraft.ranked_request` (`tuple[str, int]`) with the existing `RankedSet`-shaped request type. `SpecPatch` is persisted inside a thread's `PendingClarification`, so read the old tuple shape for one release (threads expire after the TTL) or migrate on load.

Found by the 2026-10-01 PRD/ADR review (Standards S5: plans as untyped objects; `ranked_request` duplicating `RankedSet`).

Spec: ADR 0005 (closed workflows, typed tasks).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
