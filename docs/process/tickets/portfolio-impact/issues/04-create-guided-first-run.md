# 04 — Create a guided first-run experience

**What to build:** An empty chat is replaced by three one-click stories a recruiter can run immediately: verify a quarterly fact, compare four quarters, and rank then inspect filings. The current analysis spec is visible as chips, trust labels are human-readable, and ambiguous metric clarification is answered by clicking a candidate.

**Blocked by:** 03 — Make public sessions safe by default.

**Status:** resolved

- [x] Three guided stories submit complete, demoable questions without typing.
- [x] Intent, banners, and runtime mode use human copy rather than machine slugs.
- [x] Active companies, metrics, periods, and operations appear as compact chips on the thread.
- [x] Pending clarification candidates are clickable and resume the held analysis.

## Answer

`GUIDED_STORIES` in `app.py` are one-click buttons: pretax lookup, last-four-quarters revenue, rank-and-lookup R&D, plus a filing-change story. Intent badges use `intent_label`. Runtime copy is "Guided demo" / "Live SEC". `spec_chips` render the active analysis. Clarification candidates are buttons that resume the held patch.

## Comments

- Agent: a fourth story covers filing change so tickets 08/09 are demoable from an empty chat.
