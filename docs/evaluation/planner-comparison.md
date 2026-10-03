# Rules planner vs LLM planner

Generated `2026-10-03T18:33:09.678331+00:00` on the recorded runtime, over 219 cases: 28 scorecard questions and 122 development cases ([`planner-cases.json`](planner-cases.json), [`planner-cases-v2.json`](planner-cases-v2.json)), and 69 held-out cases ([`planner-cases-held-out.json`](planner-cases-held-out.json)). Every case was labelled before a planner ran on it. The held-out cases were written by a separate session after the planner changes, and were not read by whoever changed a planner until this run.

Each case is a conversation run end to end with only the planner swapped, and is scored on the last turn's outcome (answer, clarify or refuse), intent, companies, metrics, period and operations. A case passes when every labelled field is right.

## Rules planner

| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |
| --- | ---: | ---: | ---: | ---: |
| Scorecard | 28 | 100% | 0.0% | 100% |
| Development | 122 | 100% | 0.0% | 100% |
| Held out | 69 | 91% | 0.0% | 100% |
| All | 219 | 97% | 0.0% | 100% |

Field accuracy: outcome 98%, intent 100%, tickers 99%, tickers_include 90%, metrics 99%, periods 100%, operations_include 88%.
Planner time p50 / p95: 1 ms / 3 ms over 1265 calls.

<details><summary>Cases it got wrong</summary>

- `h3_what_about_keeps_window` (run 1): outcome
- `h3_apples_to_apples` (run 1): tickers
- `h3_healthcare_market_cap` (run 1): outcome, tickers_include
- `h3_tech_top_ten_revenue` (run 1): metrics, outcome, tickers_include
- `h3_bac_jpm_ni_growth` (run 1): operations_include
- `h3_amgn_two_metrics` (run 1): outcome
- `h3_what_about_keeps_window` (run 2): outcome
- `h3_apples_to_apples` (run 2): tickers
- `h3_healthcare_market_cap` (run 2): outcome, tickers_include
- `h3_tech_top_ten_revenue` (run 2): metrics, outcome, tickers_include
- `h3_bac_jpm_ni_growth` (run 2): operations_include
- `h3_amgn_two_metrics` (run 2): outcome
- `h3_what_about_keeps_window` (run 3): outcome
- `h3_apples_to_apples` (run 3): tickers
- `h3_healthcare_market_cap` (run 3): outcome, tickers_include
- `h3_tech_top_ten_revenue` (run 3): metrics, outcome, tickers_include
- `h3_bac_jpm_ni_growth` (run 3): operations_include
- `h3_amgn_two_metrics` (run 3): outcome
- `h3_what_about_keeps_window` (run 4): outcome
- `h3_apples_to_apples` (run 4): tickers
- `h3_healthcare_market_cap` (run 4): outcome, tickers_include
- `h3_tech_top_ten_revenue` (run 4): metrics, outcome, tickers_include
- `h3_bac_jpm_ni_growth` (run 4): operations_include
- `h3_amgn_two_metrics` (run 4): outcome
- `h3_what_about_keeps_window` (run 5): outcome
- `h3_apples_to_apples` (run 5): tickers
- `h3_healthcare_market_cap` (run 5): outcome, tickers_include
- `h3_tech_top_ten_revenue` (run 5): metrics, outcome, tickers_include
- `h3_bac_jpm_ni_growth` (run 5): operations_include
- `h3_amgn_two_metrics` (run 5): outcome

</details>

## LLM planner (`gpt-5.6-terra`)

| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |
| --- | ---: | ---: | ---: | ---: |
| Scorecard | 28 | 100% | 0.0% | 100% |
| Development | 122 | 100% | 0.0% | 100% |
| Held out | 69 | 96% | 0.0% | 100% |
| All | 219 | 99% | 0.0% | 100% |

Field accuracy: outcome 99%, intent 100%, tickers 100%, tickers_include 100%, metrics 100%, periods 100%, operations_include 88%.
Planner time p50 / p95: 1046 ms / 1382 ms over 1265 calls; 1,772,155 input and 51,680 output tokens (114 reasoning), $4.16 in all, $0.0033 a call.

<details><summary>Cases it got wrong</summary>

- `h3_what_about_keeps_window` (run 1): outcome
- `h3_bac_jpm_ni_growth` (run 1): operations_include
- `h3_amgn_two_metrics` (run 1): outcome
- `h3_what_about_keeps_window` (run 2): outcome
- `h3_bac_jpm_ni_growth` (run 2): operations_include
- `h3_amgn_two_metrics` (run 2): outcome
- `h3_what_about_keeps_window` (run 3): outcome
- `h3_bac_jpm_ni_growth` (run 3): operations_include
- `h3_amgn_two_metrics` (run 3): outcome
- `h3_what_about_keeps_window` (run 4): outcome
- `h3_bac_jpm_ni_growth` (run 4): operations_include
- `h3_amgn_two_metrics` (run 4): outcome
- `h3_what_about_keeps_window` (run 5): outcome
- `h3_bac_jpm_ni_growth` (run 5): operations_include
- `h3_amgn_two_metrics` (run 5): outcome

</details>

The held-out cases measure how a planner generalises only while no planner is tuned on them: once a planner is changed because of them, they become development cases and a fresh held-out set is written before comparing again. The rules planner is deterministic, so its spread is zero by construction. The recorded runtime replays SEC data, so the comparison isolates planning; it says nothing about EDGAR freshness. See [the scorecard](scorecard.md) and [figures checked against their filings](filing-check.md).
