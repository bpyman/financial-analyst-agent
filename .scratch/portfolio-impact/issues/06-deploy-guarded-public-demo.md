# 06 — Deploy the guarded public demo

**What to build:** A stable public URL runs the fixture-first, session-isolated app so a LinkedIn visitor can try it without cloning. Deployment has a smoke check, and the storefront points at the live demo.

**Blocked by:** 02 — Add continuous verification; 03 — Make public sessions safe by default; 04 — Create a guided first-run experience; 05 — Add visual, inspectable answers.

**Status:** ready-for-agent

- [ ] A hosted Streamlit app is reachable without local setup.
- [ ] The hosted default is guided demo data with isolated threads.
- [ ] A deployment smoke check fails if the app cannot start or serve the first guided story.
- [ ] The repository homepage and storefront link to the public URL.
