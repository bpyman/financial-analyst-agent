# Interview checklist

> Archive. The interview was 20 August 2026, 5 p.m. ET, and went well. There is no remaining deadline; the project continues as a portfolio piece. Use this as a demo preflight, not a countdown.

## Highest-value preparation order

If time is short, do these in order:

1. Run the offline suite and gold rehearsal.
2. Rehearse the three-prompt walkthrough aloud with a timer.
3. Run each prompt live and inspect its provenance.
4. Practice the ten starred Q&A topics below.
5. Prepare fixture mode and a one-sentence disclosure.
6. Rehearse one failure and recovery deliberately.

## Technical preflight

From the repository root:

```powershell
uv sync
uv run pytest -q
uv run pytest -m gold
uv run ruff check .
uv run mypy
```

Run live integration checks only when the required credentials and network are available:

```powershell
uv run pytest tests/integration/test_live_openai_planner.py -m network
uv run pytest tests/integration/test_live_sec_lookup.py -m network
uv run pytest tests/integration/test_live_tavily_news.py -m network
```

Start the app:

```powershell
uv run streamlit run src/financial_analyst_agent/app.py
```

Check without displaying secret values:

- [ ] `.env` exists.
- [ ] `OPENAI_API_KEY` is configured.
- [ ] `SEC_USER_AGENT` contains a real contact identity.
- [ ] `TAVILY_API_KEY` is configured if the optional news demo will be used.
- [ ] The browser shows the expected **Live** or **Fixture** badge.
- [ ] Browser zoom and window size keep the result table and tool traces readable.
- [ ] Notifications, screen sharing, and unrelated tabs are cleaned up.
- [ ] Power and network are stable.

Do not rebuild the universe snapshot immediately before the interview unless the new snapshot has
already passed the gold suite and a full rehearsal. Reproducibility is more valuable than
last-minute freshness.

## Demo rehearsal

Time the full [`playbook.md`](playbook.md) walkthrough. Target 22–23 minutes to leave room for
interruptions.

### Prompt 1

> What was Microsoft's latest quarterly pre-tax income?

- [ ] Intent is `lookup`.
- [ ] Result is a table or fact card, not generated prose.
- [ ] Period, form, accession, concept, and filing link are visible.
- [ ] You say “directly reported standalone quarter,” not “the model found.”

### Prompt 2

> Compare TSLA and GM quarterly revenue.

- [ ] Intent is `compare`.
- [ ] Both issuers resolve correctly.
- [ ] Periods are visible.
- [ ] You can explain partial rows and period alignment without overclaiming.

### Prompt 3

> What are the top 10 technology companies and R&D spend for each?

- [ ] Intent is `rank_and_lookup`.
- [ ] Snapshot timestamp is visible.
- [ ] The ranking trace precedes fact lookup.
- [ ] You point out that CIKs, not model-generated tickers, connect the steps.
- [ ] You explain any missing row as honest partial behavior.

### Boundary prompts

- [ ] `income` produces clarification and no tool call.
- [ ] `What are the top 10 companies in AI?` produces a typed refusal.
- [ ] `What is Apple's market cap?` clearly identifies the snapshot source.

### Optional news prompt

- [ ] Tavily results were refreshed and rehearsed today.
- [ ] Returned sources are relevant and safe to show.
- [ ] You are prepared to skip news without apology if the results are weak.

## Fixture fallback

- [ ] Toggle fixture mode once before the interview and run all three prompts.
- [ ] Confirm fixture mode uses the same screen, intent, traces, and renderer.
- [ ] Memorize the disclosure:

> The fixture kill-switch is on. These are recorded facts rather than live EDGAR, but the request,
> executor, and renderer are the same application path.

- [ ] Never imply fixture results are live.
- [ ] Switch once, explain once, and continue the walkthrough.

## Ten Q&A answers to know cold

See [`technical-qa.md`](technical-qa.md).

- [ ] ★ Why closed intents instead of ReAct?
- [ ] ★ Why SEC XBRL instead of document parsing?
- [ ] ★ How is “latest quarterly” defined?
- [ ] ★ How are hallucinated numbers prevented?
- [ ] ★ Why a dated ranking snapshot?
- [ ] ★ How does rank-and-lookup preserve identity?
- [ ] ★ Why MCP if execution can be in-process?
- [ ] ★ What does fixture mode prove and not prove?
- [ ] ★ What would production architecture add?
- [ ] ★ What are the largest remaining risks?

Practice each as a 20-second answer, then a 60-second answer.

## Whiteboard from memory

Be able to draw this in under 60 seconds:

```text
User question
     |
 run_turn
     |
metric phrase gate ----> clarify / refuse
     |
closed intent
     |
deterministic executor ----> facts / ranking / news / essay tools
     |
typed TurnResult
     |
table + provenance / grounded essay / refuse
```

Add three annotations:

1. Model chooses the intent; code owns composition.
2. CIK carries company identity between tools.
3. Numbers come from tool output, not generated prose.

## Communication reminders

- Lead with the decision and why, then give implementation detail.
- Say “I chose” and name the trade-off.
- Distinguish POC behavior from production recommendations.
- Never claim worldwide or complete public-company coverage.
- Never call a snapshot value live.
- Never call a derived ratio directly reported.
- Do not apologize for explicit refusals; explain the trust boundary.
- When interrupted, answer the question and resume at the next demo transition.
- Read live values from the screen instead of recalling them from rehearsal.

## Final five minutes

- [ ] Water available; phone and desktop notifications off.
- [ ] Terminal is at the repository root.
- [ ] Streamlit app is running and browser is on the landing state.
- [ ] Design document is open at the architecture diagram.
- [ ] Fixture toggle location is known.
- [ ] No credentials, `.env` contents, or private tabs are visible.
- [ ] Take one breath before the one-sentence pitch.
