# 03 — Keep each metric's label and unit in the catalog

**What to build:** Adding a metric is one catalog entry (ADR 0005, Consequences). The rules planner now reads metric phrases from the catalog, but a metric's display facts still live elsewhere: its label in `presentation._FIELD_LABELS`, and its value kind (USD, percent, multiple, per share) in `presentation.chart_value_kind`, which derives it from `MULTIPLE_FORMULAS` / `PERCENT_FORMULAS` / `PER_SHARE_METRICS` tuples in `contracts.py`. Move label and value kind onto the catalog entry so presentation reads them from one place, and derive the `contracts.py` tuples from the catalog (or retire them).

Found by the 2026-10-01 PRD/ADR review (Standards S4). The phrase-table half is done (`016dc59`).

Spec: ADR 0004 (phrase table), ADR 0005.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
