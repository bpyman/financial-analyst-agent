# 07 — Split `graph/spec_turn.py` by reason to change

**What to build:** `graph/spec_turn.py` (about 2,300 lines) holds the wording grammar (named periods, comparison bases, follow-up edits), period dating against filings, the thread-pool fan-out, year-over-year arithmetic, ordering, and banner text. Its docstring claims resolve, run and merge only. Move the wording grammar beside `period_window.py`, and the banner text beside the presentation, so each module changes for one reason.

While there, `patch`, `wording` and `question` (with `notes` and `unrecorded`) travel together through `StructuredRequest`, `CompiledAnalysis` and `PendingClarification`; consider one type for the request as asked.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: divergent change, data clumps).

**Blocked by:** None — can start immediately, but do it apart from behaviour changes

**Status:** done

## Answer

The wording grammar (follow-up edits, named periods, windows, comparison bases, metric and overview wording; about 990 lines) is now `request_wording.py`, beside `period_window.py`, and the notes an answer carries (their banner text and the functions that choose them) are `answer_notes.py`, beside the presentation. `adjacent_quarters` joined the other fiscal-calendar arithmetic in `services/fiscal_periods.py`. `graph/spec_turn.py` keeps resolving, period dating, the fan-out, change rows, merging and ordering, at about 1,320 lines, and its docstring says so. The move changes no behaviour: the rules planner scores the same on all 219 evaluation cases before and after. Names that now cross modules are public, and their importers import them from the new modules; nothing is re-exported from `spec_turn`. One type for the request as asked was considered and left: the three types share different subsets of `patch`, `wording`, `question`, `notes` and `unrecorded`, and `PendingClarification` is stored in thread checkpoints, so folding them is a schema change for stored threads, to be done apart from this move.
