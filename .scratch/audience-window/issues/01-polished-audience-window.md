# 01 — Polished audience window

**Status:** ready-for-agent

## Problem Statement

The Thursday demo is a single Streamlit window that already answers lookup, compare, rank, rank-and-lookup, explain, news-and-explain, and refuse through `run_turn`. On screen it still looks like a developer console: raw tool-trace JSON, snake_case table dumps, unformatted dollar amounts, ISO dates, empty `rank` columns on lookup, a red stock Ask button, and an expanded sidebar. Rohit cannot read a quarterly fact as an analyst would. Blake cannot present the agent as a well-designed system without apologizing for the chrome.

## Solution

Keep Streamlit as the only audience window and keep `run_turn` as the only feature seam. Restyle that window into a dense dark terminal: third-party shadcn components for the hero chrome, a dark Streamlit theme underneath, formatted dates and dollar figures, a quarterly-fact card instead of JSON-as-answer, tables that drop empty columns, domain field names shown first then humanized, traces collapsed, kill-switch obvious with the sidebar shut, and a form that submits on Enter. Numbers still come from filings and the universe snapshot, not from the model. The product still returns the latest standalone quarter; the UI must not pretend a named historical quarter was selected.

## User Stories

1. As Blake, I want the live demo window to look like a dense financial terminal, so that Thursday is about judgment and not about apologizing for Streamlit defaults.
2. As Rohit, I want the quarterly fact to be the first thing I read after Ask, so that I can evaluate the number before I inspect the agent.
3. As Rohit, I want intent still visible on screen, so that I can see the closed planner working.
4. As Rohit, I want tool traces one click away and collapsed by default, so that traces exist for the “impressive agent” conversation without dominating the pane.
5. As Blake, I want lookup, compare, rank, rank-and-lookup, explain, news-and-explain, and refuse to share one shell, so that I do not switch UIs mid-demo.
6. As an analyst, I want a lookup turn to show one quarterly fact as a large USD amount, company, ticker, metric, and latest-standalone-quarter period, so that I do not have to parse a dataframe row.
7. As an analyst, I want provenance (form, accession, concept, filing URL) as labeled metadata on that card, so that I can verify the 10-Q without opening JSON.
8. As Blake, I want the lookup hero layout treated as a starting arrangement, so that we can nudge spacing later without treating pixels as spec.
9. As Rohit, I want rank turns to show snapshot members in a dense table with formatted market caps, so that “top 10 healthcare” is readable.
10. As Rohit, I want the universe snapshot as-of timestamp formatted and labeled UTC, so that freeze time is honest and not ISO soup.
11. As Rohit, I want rank-and-lookup to show rank plus the quarterly fact per row when present, so that composition is visible in one table.
12. As an analyst, I want a missing quarterly fact on a ranking row to stay a partial row, so that one 10-Q miss does not sink the table.
13. As Rohit, I want compare turns to show period-aligned formula results with compact USD components or percentages as appropriate, so that operating margin is a ratio and revenue is money.
14. As an analyst, I want a period-mismatch or zero-denominator compare row to keep the good company, so that partial compare still teaches the lock.
15. As Rohit, I want essay turns in the same shell with the model-analysis banner, so that qualitative answers are labeled as model text.
16. As Rohit, I want news citations as title, URL, and formatted published time when parseable, so that news-and-explain is grounded.
17. As an analyst, I want an unparseable news timestamp left as the original string, so that the UI does not invent a date.
18. As Rohit, I want refuse turns as a clear error in the same shell, so that “top 10 AI” still shows the allowed industry names.
19. As Blake, I want a configuration error (missing keys) still shown in the window, so that a dead live runtime is obvious before the interview starts.
20. As Rohit, I want dollar figures as compact USD (`$112.19 B`), so that a 12-digit Decimal is scannable.
21. As Rohit, I want the same compact USD rule on market cap and every other dollar figure, so that rank and lookup do not use two money languages.
22. As Rohit, I want amounts under one million as grouped dollars with no suffix, so that small figures are not written `$0.50 M`.
23. As Rohit, I want compact scales at 1e12 / 1e9 / 1e6 with two decimal places and half-up rounding, so that `$112.19 B` is a rule, not a one-off.
24. As Rohit, I want margins as percentages with one decimal place (`28.4%`), so that a ratio is not dressed up as money.
25. As Rohit, I want a partial row’s value left blank rather than `$None`, so that missing data is not a fake number.
26. As Rohit, I want date-only period bounds as `MMM D, YYYY`, so that a quarterly fact’s start and end are readable.
27. As Rohit, I want datetimes without seconds, in UTC, with a UTC label, so that freeze as-of does not look local.
28. As Rohit, I want every on-screen date to use those rules, so that tool traces, banners, tables, and citations do not mix ISO and English.
29. As an analyst, I want a table column omitted when every cell on this turn is empty, so that lookup does not show `rank`.
30. As an analyst, I want `reason` kept when any row on this turn has it, so that partial compare and rank-and-lookup stay honest.
31. As Rohit, I want column headers to show the domain field name first, then a humanized label, so that `company_name (Company)` still matches the code we will discuss.
32. As Rohit, I want reason cells to show the domain code first, then the humanized phrase — `missing_fact (Missing fact)` — so that the reliability locks stay named.
33. As Rohit, I want the same treatment for `period_mismatch`, `ambiguous_concept`, and `zero_denominator`, so that compare failures are not raw snake_case alone.
34. As Blake, I want the fixture kill-switch still in the sidebar, so that the existing announce-out-loud path does not move.
35. As Blake, I want the sidebar collapsed by default, so that the answer pane is full-width when the interview starts.
36. As Blake, I want a header status pill (`Live` / `Fixture`) with the sidebar shut, so that I cannot accidentally present a cassette as live EDGAR.
37. As Blake, I want the existing kill-switch banner when Fixture is on, so that the gold rehearsal script still has a line to say out loud.
38. As Rohit, I want a collapsed tool header of tool name plus a one-line identity, so that I know what `get_financials` ran before I expand it.
39. As Rohit, I want the expanded tool body as labeled key-value, not a JSON blob, so that provenance is readable and still a trace.
40. As Blake, I want Ask in a form that submits on Enter, so that I am not hunting a mouse mid-prompt.
41. As Blake, I want a spinner while the turn runs, so that rank-and-lookup’s per-row SEC work does not look hung.
42. As Blake, I want double-submit disabled while a turn is running, so that I do not fire two live OpenAI/SEC turns.
43. As Rohit, I want the input labeled “Ask a question”, so that the window reads as an analyst prompt, not a form field named Question.
44. As Rohit, I want the closed metric catalog listed under the input (reported metrics and allowed formulas), domain name then humanized, so that I know what the agent will fetch.
45. As Blake, I want the gold Google net-income query still prefilled, so that the first Ask is one keystroke.
46. As Blake, I do not want one-click gold prompt chips, so that the demo stays a typed question, not a button panel.
47. As Rohit, I want the period on a quarterly fact labeled as the latest standalone quarter, so that a user question like “Q1 2020” is not silently treated as a selected period.
48. As Blake, I want Streamlit’s Deploy control hidden, so that the toolbar does not look like a Community Cloud draft.
49. As Rohit, I want filing `source_url` clickable, so that I can open the 10-Q from the card or table.
50. As Rohit, I want compare component provenance still available from the tool trace, so that Decimal division can be audited without a second JSON dump in the hero.
51. As Blake, I want live and fixture to share this renderer, so that the kill-switch does not resurrect a second UI.
52. As a developer, I want presentation formatting unit-tested without booting Streamlit, so that `$112.19 B` and `Aug 17, 2026, 4:00 PM UTC` cannot regress behind CSS.
53. As a developer, I want existing gold tests to keep going through `run_turn`, so that a prettier window cannot change membership, XBRL selection, or refuse behavior.
54. As Blake, I want a dark canvas with a blue primary (not Streamlit red), so that Ask matches the target terminal instead of the default theme.
55. As Rohit, I want thin borders and sharp corners, so that widgets feel like a terminal, not a consumer app.
56. As an analyst, I want refuse and Fixture states in the theme’s red path, and Live in green, so that mode and failure are visible at a glance.
57. As Blake, I want shadcn used for the quarterly-fact hero and status chrome, so that we are not hand-rolling a CSS kit.
58. As a developer, I want native Streamlit dataframe, sidebar, and form kept, so that rank/compare tables and the kill-switch stay Streamlit widgets under the same dark theme.
59. As Rohit, I want empty main content (no cached turn) to show the ask field and metric list only, so that I never see an empty table.
60. As Blake, I want this change presentation-only, so that ADR 0002 membership and historical-period lookup stay future work.

## Implementation Decisions

- Presentation only. Do not change `run_turn`, planner intents, MCP tools, quarterly-fact lookup, snapshot membership, or numeral lock.
- Third-party kit is streamlit-shadcn-ui for the quarterly-fact hero and status chrome (metric/card/pill). Native Streamlit remains for dataframe, sidebar toggle, form, expander, banners, and essay markdown.
- Dark Streamlit theme file under the kit: inherit dark base; near-black canvas; widget fill near `#181818`; primary blue `#3b82f6`; sharp radius; widget borders on; Inter; toolbar minimal so Deploy is gone. Green/red palette for Live vs Fixture/refuse. Do not vendor a Bloomberg stylesheet.
- One shell for every renderer kind. Lookup’s large amount + provenance row is a starting layout, not a pixel spec.
- Introduce a presentation mapping from a turn result to display records (formatted strings, visible columns, header labels, reason labels, freeze as-of, trace summaries). Streamlit and shadcn only paint that mapping. This is the new testable seam; keep it free of widget calls.
- Compact USD: suffix T/B/M at 1e12 / 1e9 / 1e6; two decimal places; round half up; `$` prefix; space before the letter; below 1e6 grouped dollars and no suffix. Apply to every dollar figure including market cap. Currency other than USD is not in scope (today’s facts are USD).
- Margins (gross / operating / net) display as a percentage with one decimal place, not compact USD.
- Date-only values: `MMM D, YYYY`. Datetimes: same date plus time without seconds, UTC, with a `UTC` label. Apply to period start/end, freeze as-of, filed-style dates if shown, and news published when the string parses; otherwise keep the original published string.
- Omit a table column when every cell on this turn is empty or null. Do not hard-hide `rank` on lookup by special case if the empty-column rule already drops it.
- Header and reason display: domain identifier first, humanized label in parentheses. Reasons: `missing_fact (Missing fact)`, `period_mismatch (Period mismatch)`, `ambiguous_concept (Ambiguous concept)`, `zero_denominator (Zero denominator)`.
- Metric legend under the input is the closed catalog: reported `revenue`, `cost_of_revenue`, `gross_profit`, `operating_expenses`, `operating_income`, `net_income` and formulas `gross_margin`, `operating_margin`, `net_margin`, each domain name then humanized.
- Input label is “Ask a question”. Gold Google latest-quarter net income query stays the default value. No prompt chips.
- Ask lives in a form (Enter submits). Show a spinner for the duration of `run_turn`. Prevent a second submit until that call returns. Cache the turn result in session state; reruns without a new submit must not call `run_turn` again.
- Sidebar starts collapsed. Kill-switch toggle stays in the sidebar. Header pill shows Live or Fixture. Fixture still shows the existing announce-out-loud banner.
- Tool expanders start collapsed. Header is tool name plus a short identity from args (company/metric or equivalent). Body is labeled key-value of args and provenance, with the same date and money formatting, not a raw JSON widget.
- Period copy on a quarterly fact: “Latest standalone quarter” plus the formatted start and end. Do not echo a user-typed historical quarter as if it were selected. No period picker.
- Filing source URL is a link. Intent remains visible as a chip.
- Live and fixture share this renderer. Kill-switch still only swaps runtime adapters.

## Testing Decisions

Good tests assert observable display records and shell behavior, not shadcn internals, CSS selectors, or Streamlit widget trees. Do not re-test XBRL selection, ranking membership, or refuse catalogs already covered by gold and `run_turn` tests.

**Seam 1 (existing, keep):** the Streamlit main loop. Prior art: the current app test that fakes Streamlit, asserts `run_turn` runs once per Ask, and that a cached turn result is rendered on the next rerun. Extend that fake for form submit and collapsed-sidebar page config if those calls are part of the loop; do not assert HTML.

**Seam 2 (new, primary for this spec):** a pure presentation mapping from a turn result (and its table rows, banners, citations, traces) to formatted display records. This is the highest seam that can lock money, dates, empty columns, and domain-then-humanized labels without a browser. Unit tests supply a lookup quarterly fact, a rank table with market caps, a compare row with a margin, a partial row with a reason, a freeze as-of datetime, and an unparseable news timestamp. Expected values are literals (`$112.19 B`, `Jun 30, 2020`, `Aug 17, 2026, 4:00 PM UTC`, columns without `rank` when rank is empty, `missing_fact (Missing fact)`).

Do not add a third seam for CSS or for shadcn component props. Gold tests stay on `run_turn` with fixture runtime and must remain green with no assertion changes required by this spec.

## Out of Scope

- Historical-period lookup or a date picker (latest standalone quarter only).
- ADR 0002 membership gating on lookup/compare.
- Leaving Streamlit, faking Bloomberg chrome (markets list, analog clock, top nav), or copying a proprietary terminal stylesheet.
- Prompt chips, chat history, or multi-turn memory.
- Changing MCP payloads, planner output, or essay numeral lock.
- Non-USD display, compact-money localization, or local-timezone freeze times.
- Pixel-perfect lock of the lookup hero (starting layout only).
- Screenshot / browser tests.

## Further Notes

The target aesthetic is a dark, dense, blue-accent terminal used as visual language, not as a product to clone. Compact USD rounding will show `$112.19 B` for `112193000000` (112.193 billion, two decimals, half up). Freeze timestamps on the wire include seconds; drop seconds and microseconds in display. If shadcn and native dataframes clash visually, prefer matching the dark theme file over replacing the dataframe.
