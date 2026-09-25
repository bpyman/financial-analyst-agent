# streamlit-redirect

This branch is the old Streamlit Community Cloud app for
[Financial Analyst Agent](https://github.com/bpyman/financial-analyst-agent). It holds
one page, "This demo has moved", so links sent out before the move keep working. The
demo itself now lives on `master` (ADR 0006).

It is an orphan branch: it shares no history with `master` and is never merged.

| File | What it is |
| --- | --- |
| `streamlit_app.py` | The page: one message and one button |
| `requirements.txt` | Streamlit only |
| `.streamlit/config.toml` | The dark theme of the new window |

## The new address

The button opens the `DEMO_URL` secret. Set it in the app's settings on Community
Cloud, as a quoted top-level string:

```toml
DEMO_URL = "https://<project>.vercel.app"
```

Community Cloud exports top-level string secrets as environment variables, and the page
reads the variable. Until `DEMO_URL` is set, or if it is not an `https://` URL, the
button opens the GitHub repo and the page says the new address is not live yet.

The Community Cloud steps are in `docs/deploy.md` on `master`, under "Repointing the
Streamlit app".

## Run it locally

```text
python -m venv .venv
.venv/bin/pip install -r requirements.txt
DEMO_URL=https://example.com .venv/bin/streamlit run streamlit_app.py
```
