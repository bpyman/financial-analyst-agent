# Evaluation scorecard

Generated `2026-09-25T07:37:44.412828+00:00` against the recorded runtime.

- Pass rate: **9/9** (100%)
- Latency p50 / p95: **2 ms** / **6 ms**
- Approximate live cost per scenario: **not measured** (published card is the recorded runtime)
- Planner: `recorded DemoCompleter`

| Case | Category | Result | ms |
| --- | --- | --- | ---: |
| `lookup_msft_pretax` | intent_routing | pass | 7 |
| `compare_tsla_gm` | intent_routing | pass | 2 |
| `rank_tech_rd` | intent_routing | pass | 2 |
| `refuse_unknown_metric` | ambiguity_refusal | pass | 0 |
| `clarify_profit` | ambiguity_refusal | pass | 0 |
| `follow_up_add_apple` | stateful_follow_up | pass | 4 |
| `numeral_lock_explain` | numeral_lock | pass | 1 |
| `numeral_lock_invented_number` | numeral_lock | pass | 1 |
| `filing_change_mda` | filing_change | pass | 6 |

SEC JSON is disk-cached on the live path; retries and 429/5xx backoff live in `SECClient`. This is not a full production operations report.
