# Ambiguous metric phrases clarify; they do not fetch

A metric phrase is taken from the **user question**, not from `plan.metric`. Longest closed-table span wins (word boundaries). An exact catalog name or unique alias may run tools. An **ambiguous metric** returns `RendererKind.CLARIFY` with only those humanized names, no tools, same planned intent; the analyst retypes. An **unknown metric** still refuses with the full catalog. `parse_metric` unknown strings become `UnknownMetricError` — that error is not the clarify path. Gold prompt 2 says **net income**; the interview brief’s “reported income” is left ambiguous on purpose. The phrase table grows when the catalog grows; it is not inferred from stems (`operating` is not a metric). Trusting the planner’s slug was rejected: the model will guess `net_income` for “income” and skip the pane.

## Phrase table

Unique (1:1), longest span first: `cost of goods and services` / `cost of goods sold` / `cost of sales` / `cost of revenue` / `cogs` → `cost_of_revenue`; `selling general and administrative` / `sg&a` / `sga` → `selling_general_and_administrative`; `research and development` / `r&d` → `research_and_development`; `r&d to sales` / `r&d intensity` → `rd_to_sales`; `sg&a ratio` → `sga_ratio`; `operating expenses` / `operating costs` / `opex` → `operating_expenses`; `operating profit margin` → `operating_margin`; `operating income` / `operating profit` / `operating earnings` / `ebit` → `operating_income`; `operating margin` / `operating margins` / `ebit margin` → `operating_margin`; `gross profit margin` → `gross_margin`; `gross profit` → `gross_profit`; `gross margin` / `gross margins` → `gross_margin`; `effective tax rate` / `tax rate` → `effective_tax_rate`; `income tax expense` / `income tax` / `tax expense` → `income_tax_expense`; `interest coverage` → `interest_coverage`; `interest expense` / `interest costs` → `interest_expense`; `pretax income` / `pre-tax income` / `income before tax` → `pretax_income`; `net profit margin` → `net_margin`; `net income` / `net profit` / `net earnings` / `earnings` / `bottom line` → `net_income`; `net margin` / `net margins` → `net_margin`; `net sales` / `sales` / `revenue` → `revenue`; `market capitalization` / `market cap` / `mkt cap` → `market_cap`. Slugs (`net_income`, …) are unique too.

Ambiguous (1:N), only if no unique span matched: `profit margin` → Gross margin, Operating margin, Net margin; `profit` → Gross profit, Operating income, Net income; `income` → Net income, Operating income; `margin` → Gross margin, Operating margin, Net margin; `gross` → Gross profit, Gross margin; `net` → Net income, Net margin; `interest` → Interest expense, Interest coverage; `tax` → Income tax expense, Effective tax rate.

Two unique catalog names in one question are also an ambiguous metric (those names). `costs`, `ROE`, `EBITDA` stay unknown.

## Considered Options

- **LLM writes a clarifying question** — rejected: the catalog owns the candidate set.
- **Hold a pending plan / chips** — rejected: `run_turn` stays one-shot; no multi-turn memory.
- **Match `plan.metric` only** — rejected: live OpenAI resolves collisions silently.
- **Alias `reported income` → net income** — rejected: operating income is also reported.
- **Treat `operating` as ambiguous** — rejected: the word appears in non-metric questions.
