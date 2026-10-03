# 06 — One table for what each clarification kind does

**What to build:** The same four-way branch on `ambiguous_metric`, `ambiguous_mode`, `ambiguous_company` and `ambiguous_comparison` appears in `graph/clarify.py` (reading the answer, resuming the question, asking again) and in `presentation.py` (the prompt). Adding a fifth kind means editing every branch. Gather each kind's prompt, answer reader, resume and "ask again" note in one place keyed by kind.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: repeated switches).

Spec: ADR 0004, ADR 0005, ADR 0010.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
