# 01 — Carry CIK identity through the analysis spec

**What to build:** An analysis spec holds CIKs for every named company before any provider call, as `CONTEXT.md` ("Resolved means CIKs") and ADR 0005 ("A spec must be resolved before any provider call") say. Today `graph/analysis_spec._resolve_company` keeps `cik=""` for a company the ranking snapshot does not hold, and `_base_tasks` / `calendar_groups` compile `company.query` (the analyst's text) even when a CIK was resolved, so the facts port re-resolves text per cell.

Resolve a snapshot miss through SEC identity (the runtime's `filings` port has the ticker map), keep an unresolvable name as a typed miss row (ADR 0002: other compare rows stay), and compile tasks by CIK.

Found by the 2026-10-01 PRD/ADR review (Standards S2). A trial that only compiled `company.cik or company.query` regressed the recorded demo (the four-quarter comparison lost its quarters; charts and traces changed), because per-company state is keyed on the query text. The work is:

- Key per-company state on CIK, not `company.query.casefold()`: `PeriodSelection.company_report_dates`, `calendar_groups`, `materialize_period_dates`, `_fill_identity`, `_companies_named_in`, and the trend/overview helpers in `graph/spec_turn.py`.
- Name a failed cell from the spec's resolved company, not from the task's query string.
- Key `evidence_store.fact_evidence_id` on CIK, so "Google" and "GOOGL" share evidence (review smell: evidence keyed on query text).
- Bundle the identity that travels positionally through `services/fact_selector.py` (`company_name, ticker, cik`, plus `currency`) into one type while those signatures are open (review smell: data clump).
- Teach the test fakes that answer by company name to accept CIKs, or give them a small name→CIK map.

Spec: `CONTEXT.md` (Analysis spec), ADR 0002, ADR 0005, `docs/design.md` ("identity is carried as SEC CIK").

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
