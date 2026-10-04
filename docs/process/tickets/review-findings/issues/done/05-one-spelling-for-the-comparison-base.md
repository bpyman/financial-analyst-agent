# 05 — One spelling for the comparison base

**What to build:** The comparison base (`CONTEXT.md`) is spelt `"year_over_year"` / `"sequential"` in `graph/state.py` and `graph/spec_turn.py`, but `"yoy"` / `"sequential"` on `TableRow.comparison` (`contracts.py`), so `planner_evaluation.observe` translates between them and `spec_turn._with_comparison` takes a bare `str`. Give the comparison base one `Literal` type used by the request, the operation and the row, and remove the translation.

The row value reaches stored threads and the web window (`comparison` in presentation JSON), so keep reading the old `"yoy"` on load.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: primitive obsession).

Spec: `CONTEXT.md` (Comparison base), ADR 0009, ADR 0010.

**Blocked by:** None — can start immediately

**Status:** done

## Answer

The comparison base is `contracts.ComparisonBase`, `Literal["year_over_year", "sequential"]`, used by `StructuredRequest.comparison`, `TableRow.comparison`, `comparison_asked`, `_with_comparison`, the change rows and the clarification answer. Change rows now say `"year_over_year"`, so `planner_evaluation.observe` reads them without translating, and the presentation's change labels, column order and wide-table keys (`change:revenue:year_over_year`) are typed by it; the fallbacks for an unknown kind are gone. `TableRow` reads the old `"yoy"` of a stored thread as `"year_over_year"` (tested in `tests/unit/test_thread_store.py`).
