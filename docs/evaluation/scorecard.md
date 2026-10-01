# Evaluation scorecard

Generated `2026-10-01T14:16:58.291120+00:00` against the recorded runtime.

- Pass rate: **30/30** (100%)
- Latency p50 / p95: **6 ms** / **31 ms**
- Approximate live cost per scenario: **not measured** (published card is the recorded runtime)
- Planner: `recorded DemoCompleter`

| Case | Category | Result | ms |
| --- | --- | --- | ---: |
| `lookup_msft_pretax` | intent_routing | pass | 205 |
| `compare_tsla_gm` | intent_routing | pass | 7 |
| `rank_tech_rd` | intent_routing | pass | 13 |
| `refuse_unknown_metric` | ambiguity_refusal | pass | 0 |
| `clarify_profit` | ambiguity_refusal | pass | 1 |
| `follow_up_add_apple` | stateful_follow_up | pass | 8 |
| `numeral_lock_explain` | numeral_lock | pass | 2 |
| `numeral_lock_invented_number` | numeral_lock | pass | 2 |
| `filing_change_mda` | filing_change | pass | 10 |
| `window_four_quarters` | periods_and_calendars | pass | 11 |
| `named_fiscal_quarter` | periods_and_calendars | pass | 3 |
| `calendars_differ` | periods_and_calendars | pass | 18 |
| `unreported_future_quarter` | periods_and_calendars | pass | 1 |
| `sub_quarter_period` | periods_and_calendars | pass | 3 |
| `growth_chart` | growth_and_trends | pass | 20 |
| `growth_lines_two_companies` | growth_and_trends | pass | 17 |
| `overview_with_trends` | growth_and_trends | pass | 31 |
| `formula_margin` | growth_and_trends | pass | 6 |
| `ranking_ordered_by_metric` | rankings | pass | 6 |
| `ranking_by_market_cap` | rankings | pass | 3 |
| `fund_is_not_a_company` | rankings | pass | 3 |
| `clarify_income` | ambiguity_refusal | pass | 1 |
| `advice_declined` | ambiguity_refusal | pass | 0 |
| `off_topic_refused` | ambiguity_refusal | pass | 4 |
| `follow_up_metric_and_company` | stateful_follow_up | pass | 47 |
| `follow_up_sort` | stateful_follow_up | pass | 15 |
| `follow_up_swap_company` | stateful_follow_up | pass | 8 |
| `follow_up_start_over` | stateful_follow_up | pass | 6 |
| `filing_change_latest` | filing_change | pass | 12 |
| `news_kept_apart` | news | pass | 5 |

The cases run on the recorded runtime, so they are repeatable and need no keys. [Figures checked against their filings](filing-check.md) is the live counterpart: each figure the window shows, found in the text of the 10-Q it cites.

SEC JSON is disk-cached on the live path; retries and 429/5xx backoff live in `SECClient`. This is not a full production operations report.
