The 20 August 2026 interview is done and went well. There is no deadline. Continue this as a portfolio project; do not time-box or drop work for Thursday.

## Agent skills

### Issue tracker

The product PRD is `prd.md` at the repo root. Tickets live under `.scratch/<feature>/issues/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default role strings: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Snapshot membership

When ranking includes a fund, SPAC, BDC, note, or other non-operating listing, add its CIK to `src/financial_analyst_agent/data/ineligible_issuers.json` per `docs/adr/0001-snapshot-membership.md`.

## Cursor Cloud specific instructions

This is a single Python package managed with `uv` (Python 3.12). The startup update script keeps `uv` installed and runs `uv sync`, so the `.venv` is already provisioned. Prefix commands with `uv run`. Standard commands live in `README.md` and `pyproject.toml`; the notes below are the non-obvious caveats.

- The only long-running process is the Streamlit UI (`app.py`), which runs the whole agent in-process via `run_turn`. The FastMCP server (`mcp_server.py`) and the snapshot builder are optional and not required to exercise the product.
- Run the app offline with no API keys by setting `APP_MODE=fixture` (the sidebar "Fixture kill-switch"), which swaps every adapter for recorded cassettes: `APP_MODE=fixture uv run streamlit run src/financial_analyst_agent/app.py --server.headless true`. Live mode (`APP_MODE=live`, the default) additionally needs `OPENAI_API_KEY`, `SEC_USER_AGENT`, and `TAVILY_API_KEY` in `.env`.
- Tests default to offline: `pytest` config sets `addopts = -m 'not network'`, so `uv run pytest -q` and `uv run pytest -m gold` need no network or secrets. Only `uv run pytest -m network` (the `tests/integration/test_live_*.py` files) requires live API keys.
- Lint/type-check with `uv run ruff check .` and `uv run mypy` (mypy is strict).

