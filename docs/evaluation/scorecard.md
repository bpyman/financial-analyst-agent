# Evaluation scorecard

Generated `2026-09-27T23:05:55.787493+00:00` against the recorded runtime.

- Pass rate: **9/9** (100%)
- Latency p50 / p95: **5 ms** / **10 ms**
- Approximate live cost per scenario: **not measured** (published card is the recorded runtime)
- Planner: `recorded DemoCompleter`

| Case | Category | Result | ms |
| --- | --- | --- | ---: |
| `lookup_msft_pretax` | intent_routing | pass | 120 |
| `compare_tsla_gm` | intent_routing | pass | 5 |
| `rank_tech_rd` | intent_routing | pass | 7 |
| `refuse_unknown_metric` | ambiguity_refusal | pass | 0 |
| `clarify_profit` | ambiguity_refusal | pass | 2 |
| `follow_up_add_apple` | stateful_follow_up | pass | 8 |
| `numeral_lock_explain` | numeral_lock | pass | 2 |
| `numeral_lock_invented_number` | numeral_lock | pass | 2 |
| `filing_change_mda` | filing_change | pass | 10 |

SEC JSON is disk-cached on the live path; retries and 429/5xx backoff live in `SECClient`. This is not a full production operations report.
