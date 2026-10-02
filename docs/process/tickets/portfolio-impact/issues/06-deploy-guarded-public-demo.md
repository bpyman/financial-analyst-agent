# 06 — Deploy the guarded public demo

**What to build:** A stable public URL runs the fixture-first, session-isolated app so a LinkedIn visitor can try it without cloning. Deployment has a smoke check, and the storefront points at the live demo.

**Blocked by:** 02 — Add continuous verification; 03 — Make public sessions safe by default; 04 — Create a guided first-run experience; 05 — Add visual, inspectable answers.

**Status:** resolved

- [x] A hosted Streamlit app is reachable without local setup.
- [x] The hosted default is guided demo data with isolated threads.
- [x] A deployment smoke check fails if the app cannot start or serve the first guided story.
- [x] The repository homepage and storefront link to the public URL.

## Answer

Hosted demo: [https://financial-analyst-agent-project.streamlit.app](https://financial-analyst-agent-project.streamlit.app). Fixture-first, isolated threads, `APP_MODE=fixture` / `PUBLIC_DEMO=true`. README, `docs/deploy.md`, and the GitHub homepage point at that URL. `tests/test_demo_smoke.py` covers the first guided story locally; live smoke confirmed the pretax-income table.

## Comments

- Agent: Community Cloud apps sleep when idle; the first visitor may need to wake the app.
