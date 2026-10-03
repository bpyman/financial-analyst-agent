# Rules planner vs LLM planner

Generated `2026-10-03T12:54:21.199566+00:00` on the recorded runtime. Cases: [`planner-cases.json`](planner-cases.json) (78: 28 scorecard questions, 50 held-out paraphrases labelled before either planner ran on them).

Each case is a conversation run end to end with only the planner swapped, and is scored on the last turn's outcome (answer, clarify or refuse), intent, companies, metrics, period and operations. A case passes when every labelled field is right.

## Rules planner

| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |
| --- | ---: | ---: | ---: | ---: |
| Scorecard | 28 | 96% | 0.0% | 100% |
| Held out | 50 | 88% | 0.0% | 100% |
| All | 78 | 91% | 0.0% | 100% |

Field accuracy: outcome 97%, intent 97%, tickers 96%, tickers_include 89%, metrics 98%, periods 83%, operations_include 100%.
Planner time p50 / p95: 1 ms / 2 ms over 430 calls.

<details><summary>Cases it got wrong</summary>

- `follow_up_metric_and_company` (run 1): metrics
- `ho_nvda_past_four` (run 1): periods
- `ho_pfe_mrk_six_quarters` (run 1): periods
- `ho_banks_market_cap` (run 1): outcome, tickers_include
- `ho_follow_include_oracle` (run 1): tickers
- `ho_follow_swap_abbvie` (run 1): outcome, tickers
- `ho_msft_filing_paraphrase` (run 1): intent
- `follow_up_metric_and_company` (run 2): metrics
- `ho_nvda_past_four` (run 2): periods
- `ho_pfe_mrk_six_quarters` (run 2): periods
- `ho_banks_market_cap` (run 2): outcome, tickers_include
- `ho_follow_include_oracle` (run 2): tickers
- `ho_follow_swap_abbvie` (run 2): outcome, tickers
- `ho_msft_filing_paraphrase` (run 2): intent
- `follow_up_metric_and_company` (run 3): metrics
- `ho_nvda_past_four` (run 3): periods
- `ho_pfe_mrk_six_quarters` (run 3): periods
- `ho_banks_market_cap` (run 3): outcome, tickers_include
- `ho_follow_include_oracle` (run 3): tickers
- `ho_follow_swap_abbvie` (run 3): outcome, tickers
- `ho_msft_filing_paraphrase` (run 3): intent
- `follow_up_metric_and_company` (run 4): metrics
- `ho_nvda_past_four` (run 4): periods
- `ho_pfe_mrk_six_quarters` (run 4): periods
- `ho_banks_market_cap` (run 4): outcome, tickers_include
- `ho_follow_include_oracle` (run 4): tickers
- `ho_follow_swap_abbvie` (run 4): outcome, tickers
- `ho_msft_filing_paraphrase` (run 4): intent
- `follow_up_metric_and_company` (run 5): metrics
- `ho_nvda_past_four` (run 5): periods
- `ho_pfe_mrk_six_quarters` (run 5): periods
- `ho_banks_market_cap` (run 5): outcome, tickers_include
- `ho_follow_include_oracle` (run 5): tickers
- `ho_follow_swap_abbvie` (run 5): outcome, tickers
- `ho_msft_filing_paraphrase` (run 5): intent

</details>

## LLM planner (`gpt-5.6-terra`)

| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |
| --- | ---: | ---: | ---: | ---: |
| Scorecard | 28 | 96% | 0.0% | 100% |
| Held out | 50 | 92% | 0.9% | 98% |
| All | 78 | 93% | 0.6% | 99% |

Field accuracy: outcome 100%, intent 100%, tickers 95%, tickers_include 89%, metrics 100%, periods 83%, operations_include 100%.
Planner time p50 / p95: 1019 ms / 1364 ms over 430 calls; 564,360 input and 15,111 output tokens (278 reasoning), $1.31 in all, $0.0030 a call.

<details><summary>Cases it got wrong</summary>

- `follow_up_swap_company` (run 1): tickers_include
- `ho_gs_jpm_net_income` (run 1): tickers
- `ho_tmo_dhr_stack_up` (run 1): tickers
- `ho_nvda_past_four` (run 1): periods
- `ho_pfe_mrk_six_quarters` (run 1): periods
- `ho_follow_include_oracle` (run 1): tickers
- `follow_up_swap_company` (run 2): tickers_include
- `ho_gs_jpm_net_income` (run 2): tickers
- `ho_nvda_past_four` (run 2): periods
- `ho_pfe_mrk_six_quarters` (run 2): periods
- `ho_follow_include_oracle` (run 2): tickers
- `follow_up_swap_company` (run 3): tickers_include
- `ho_gs_jpm_net_income` (run 3): tickers
- `ho_nvda_past_four` (run 3): periods
- `ho_pfe_mrk_six_quarters` (run 3): periods
- `ho_follow_include_oracle` (run 3): tickers
- `follow_up_swap_company` (run 4): tickers_include
- `ho_gs_jpm_net_income` (run 4): tickers
- `ho_nvda_past_four` (run 4): periods
- `ho_pfe_mrk_six_quarters` (run 4): periods
- `ho_follow_include_oracle` (run 4): tickers
- `follow_up_swap_company` (run 5): tickers_include
- `ho_gs_jpm_net_income` (run 5): tickers
- `ho_nvda_past_four` (run 5): periods
- `ho_pfe_mrk_six_quarters` (run 5): periods
- `ho_follow_include_oracle` (run 5): tickers

</details>

The held-out cases measure how a planner generalises only while neither planner is tuned on them: after changing a planner to pass them, write a fresh held-out set before comparing again. The rules planner is deterministic, so its spread is zero by construction. The recorded runtime replays SEC data, so the comparison isolates planning; it says nothing about EDGAR freshness. See [the scorecard](scorecard.md) and [figures checked against their filings](filing-check.md).
