# 07 — Split `graph/spec_turn.py` by reason to change

**What to build:** `graph/spec_turn.py` (about 2,300 lines) holds the wording grammar (named periods, comparison bases, follow-up edits), period dating against filings, the thread-pool fan-out, year-over-year arithmetic, ordering, and banner text. Its docstring claims resolve, run and merge only. Move the wording grammar beside `period_window.py`, and the banner text beside the presentation, so each module changes for one reason.

While there, `patch`, `wording` and `question` (with `notes` and `unrecorded`) travel together through `StructuredRequest`, `CompiledAnalysis` and `PendingClarification`; consider one type for the request as asked.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: divergent change, data clumps).

**Blocked by:** None — can start immediately, but do it apart from behaviour changes

**Status:** ready-for-agent
