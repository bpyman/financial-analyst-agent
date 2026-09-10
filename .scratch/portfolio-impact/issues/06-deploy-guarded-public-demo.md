# 06 — Deploy the guarded public demo

**What to build:** A stable public URL runs the fixture-first, session-isolated app so a LinkedIn visitor can try it without cloning. Deployment has a smoke check, and the storefront points at the live demo.

**Blocked by:** 02 — Add continuous verification; 03 — Make public sessions safe by default; 04 — Create a guided first-run experience; 05 — Add visual, inspectable answers.

**Status:** ready-for-human

- [ ] A hosted Streamlit app is reachable without local setup.
- [x] The hosted default is guided demo data with isolated threads.
- [x] A deployment smoke check fails if the app cannot start or serve the first guided story.
- [ ] The repository homepage and storefront link to the public URL.

## Answer

App code, `.streamlit/config.toml`, `.streamlit/secrets.toml.example`, and `docs/deploy.md` are ready: `APP_MODE=fixture`, `PUBLIC_DEMO=true`, isolated UUID threads. `tests/test_demo_smoke.py` runs the first guided story through fixture mode. Publishing the URL requires a Streamlit Community Cloud (or equivalent) login and then setting the GitHub homepage.

## Comments

- Agent: cannot complete the hosted URL without the owner's Streamlit account.
