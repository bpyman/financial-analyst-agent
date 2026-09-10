# Evaluation scorecard

Generated `2026-09-10T16:10:36.125491+00:00` against the fixture runtime.

- Pass rate: **9/9** (100%)
- Latency p50 / p95: **1 ms** / **5 ms**
- Approximate live cost per scenario: **not measured** (published card is the fixture path)
- Planner: `fixture DemoCompleter`

| Case | Category | Result | ms |
| --- | --- | --- | ---: |
| `lookup_msft_pretax` | intent_routing | pass | 8 |
| `compare_tsla_gm` | intent_routing | pass | 1 |
| `rank_tech_rd` | intent_routing | pass | 1 |
| `refuse_unknown_metric` | ambiguity_refusal | pass | 0 |
| `clarify_profit` | ambiguity_refusal | pass | 0 |
| `follow_up_add_apple` | stateful_follow_up | pass | 2 |
| `numeral_lock_explain` | numeral_lock | pass | 1 |
| `numeral_lock_invented_number` | numeral_lock | pass | 1 |
| `filing_change_mda` | filing_change | pass | 5 |

SEC JSON is disk-cached on the live path; retries and 429/5xx backoff live in `SECClient`. This is not a full production operations report.
