# Financial analyst agent

Thursday interview POC: one Streamlit window, closed intents, SEC XBRL facts, snapshot ranking, and labeled essays that cannot invent numbers.

The system design (diagram + ADRs) is [`docs/design.md`](docs/design.md).

## Demo

```text
uv sync
copy .env.example .env
```

Fill `OPENAI_API_KEY`, `SEC_USER_AGENT`, and `TAVILY_API_KEY` in `.env`. Then:

```text
uv run streamlit run src/financial_analyst_agent/app.py
```

Live default. Scripted prompts:

1. Microsoft pre-tax income
2. TSLA vs GM revenue
3. Top 10 tech companies R&D spend

Backup (needs fresh Tavily): *Effects of recent Strait of Hormuz closures on Exxon*

Refuse rehearsal: *What are the top 10 companies in AI?*

### Kill-switch

The sidebar **Fixture kill-switch** swaps every adapter for recorded ones and still uses the same `run_turn` renderer. **If you turn it on, say so out loud.** Do not present a cassette as live EDGAR.

`APP_MODE=fixture` in `.env` starts with the kill-switch on.

## Tests

Offline (default):

```text
uv run pytest -q
uv run pytest -m gold
```

Live (needs keys):

```text
uv run pytest tests/integration/test_live_openai_planner.py -m network
uv run pytest tests/integration/test_live_sec_lookup.py -m network
uv run pytest tests/integration/test_live_tavily_news.py -m network
```

Rebuild the ranking freeze (does not run during a demo turn):

```text
uv run build-universe-snapshot
```
