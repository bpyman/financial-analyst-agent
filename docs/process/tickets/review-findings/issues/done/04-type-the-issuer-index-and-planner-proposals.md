# 04 — Type the issuer index the turn passes around

**What to build:** The issuer index travels as `Any` and is probed with `getattr(index, "find", None)` and `callable(find)` in `graph/clarify.py`, `graph/spec_turn.py`, `guide.py` and `graph/turn_graph.py`; `planner_evaluation.MeteredCompleter.__getattr__` exists partly to keep `completer.index` reachable. Give the index a small `Protocol` (`find`, `named`, `correct`, `display_name`) and pass it typed. `turn_graph.names_index` already decides which index a turn reads; make it the one source, and drop the `getattr` probes. `run_filing_change(plan: Any)` still reads fields with `getattr` though its caller passes a typed `FilingChangeRequest`: take that type.

Planner proposals are probed the same way; ticket 02 covers typing them, so do that here only where the index work touches it.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: primitive obsession).

Spec: ADR 0010 ("One resolver").

**Blocked by:** None — can start immediately

**Status:** done

## Answer

The index is typed as `issuer_index.CompanyNames` (a `Protocol`: `find`, `named`, `display_name`), and every `getattr(index, ...)` / `callable(find)` probe in `graph/clarify.py`, `graph/spec_turn.py`, `guide.py` and `graph/turn_graph.py` is gone; `turn_graph.names_index` is the one place a turn picks its index. `run_filing_change` and `_request_refusal` take the `FilingChangeRequest` their caller passes, and the filing-change tests build one. `MeteredCompleter.__getattr__` stays: it forwards more than the index (the recorded `outside_index`). The planner proposals still probed with `getattr` are ticket 02.
