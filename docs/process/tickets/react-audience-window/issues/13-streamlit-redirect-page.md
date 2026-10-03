# 13 — Old Streamlit links land on a "moved" page

**What to build:** Links to the old Community Cloud URL keep working after cutover. A `streamlit-redirect` branch holds a single Streamlit page saying the demo has moved, with a button to the new URL (read from app secrets, with a sensible default), plus its own minimal requirements. The deploy notes tell Blake how to repoint the Community Cloud app at that branch.

Spec: ADR 0006 (Migration).

**Blocked by:** 09

**Status:** resolved

- [x] The branch exists, holds only the moved page, its requirements, and a README
- [x] The page runs locally with only its own requirements installed
- [x] The deploy notes carry the repoint steps

## Answer

The `streamlit-redirect` branch is an orphan branch (commit `489a291`, no shared history with `master`). It was created locally; the orchestrator pushes it. It holds four files:

- `streamlit_app.py`: a caption, "This demo has moved", one line, and one primary `st.link_button`. The button opens `DEMO_URL`, read from the environment, because Community Cloud exports top-level string secrets as env vars. When `DEMO_URL` is unset or is not `https://`, the button reads "View the project on GitHub" (https://github.com/bpyman/financial-analyst-agent) and the line says the new address is not live yet.
- `requirements.txt`: `streamlit==1.61.1` only.
- `.streamlit/config.toml`: the new window's dark palette (bg `#07080a`, primary `#3b82f6`), minimal toolbar, no sidebar nav.
- `README.md`: what the branch is, the `DEMO_URL` secret, and a local run.

The entry point is `streamlit_app.py` at the root, not the old `src/financial_analyst_agent/app.py`. Community Cloud cannot change a deployed app's branch in place, so the app is deleted and redeployed anyway, and the old path buys nothing.

It was verified in a throwaway venv with only its own requirements (Python 3.11, streamlit 1.61.1). `streamlit run` served `/_stcore/health` "ok" with `DEMO_URL` unset and set. Playwright at 1280 and 390 px found the right button label and href in each case, a `#07080a` background, no page errors, and no horizontal scroll.

`docs/deploy.md` has a new "Repointing the Streamlit app" section, placed before the legacy notes so ticket 14 can delete those and keep it. It covers when (after ticket 11, before ticket 14 merges, since Community Cloud redeploys on push), delete then Create app with branch `streamlit-redirect`, main file `streamlit_app.py`, and App URL `financial-analyst-agent-project`, the `DEMO_URL` secret, a check, and a fallback if the subdomain is not released yet. `tests/test_deploy_config.py::test_deploy_notes_repoint_the_old_streamlit_url_at_the_redirect_branch` pins those steps.

Not confirmed: docs.streamlit.io was blocked, so the dashboard steps come from search excerpts. Whether a deleted app's subdomain is free at once is unknown.
