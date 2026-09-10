# Hosted demo

The public audience window is a Streamlit app that defaults to recorded adapters,
isolated browser sessions, thread expiry, and cached SEC responses.

## Streamlit Community Cloud

1. Fork or connect `bpyman/financial-analyst-agent`.
2. Main file: `src/financial_analyst_agent/app.py`.
3. Copy `.streamlit/secrets.toml.example` into the app's secrets. Keep
   `APP_MODE=fixture` and `PUBLIC_DEMO=true`.
4. Confirm the first guided story (`Verify a quarterly fact`) returns a table.

Local smoke:

```text
uv run python -m pytest tests/test_demo_smoke.py -q
uv run python -m streamlit run src/financial_analyst_agent/app.py
```

The repository homepage should point at the deployed URL once it exists.
