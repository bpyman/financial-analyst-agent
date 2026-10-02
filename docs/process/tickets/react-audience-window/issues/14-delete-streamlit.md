# 14 — Delete the Streamlit window

**What to build:** Once the new window is live, `main` sheds Streamlit:
- the Streamlit app and its tests;
- the Streamlit settings and secrets example;
- the Community Cloud requirements export;
- the `streamlit`, `streamlit-shadcn-ui`, `altair`, and `pandas` dependencies.

Storefront copy, session budget, and presentation stay, because the API uses them. The PRD notes that ADR 0006 supersedes its "Streamlit is the only audience window" story.

The PR carrying this ticket stays a draft until ticket 11 is resolved. Merging it is the cutover.

Spec: ADR 0006 (Migration, cutover criteria).

**Blocked by:** 12, 13

**Status:** resolved

- [x] Nothing in `src/`, `tests/`, or the dependencies imports Streamlit, Altair, or pandas
- [x] The lockfile is regenerated with uv, not by hand
- [x] pytest, ruff, mypy, and the web checks pass
- [x] The PRD and design doc point at ADR 0006 for the window

## Answer

`master` sheds Streamlit once this PR merges. The PR stays a draft until ticket 11 is resolved, and the Community Cloud app must be repointed at `streamlit-redirect` (docs/deploy.md, "Repointing the Streamlit app") before it merges.

Deleted:
- `src/financial_analyst_agent/app.py`, `tests/test_app.py`, `tests/test_app_widgets.py`
- `.streamlit/` (config and secrets example) and the root `requirements.txt` (the Community Cloud export; nothing else read it, since Docker installs from `uv.lock`)
- `streamlit` and `streamlit-shadcn-ui`, removed with `uv remove`. `uv.lock` goes from 131 to 111 packages. `altair`, `pandas`, `pyarrow`, `numpy`, and `pillow` were only there through Streamlit, so they left with it.
- The "Legacy: Streamlit Community Cloud" section of `docs/deploy.md` and the intro link to it. "Repointing the Streamlit app" and its test stay.

Kept, because the API uses them: `storefront.py`, `session.py`, `presentation.py`. No symbol in them went unused.

Tests that guarded behaviour the API still has moved to the API or presentation seam:
- `tests/test_api.py`: the capability catalog, examples, metric groups, and example query from `/api/meta`; a failed turn streams the public message (or a configuration error's own text) and keeps prior turns; a failed turn still counts against the thread budget, including live SEC requests; a thread survives an API restart; an expired thread reloads empty and is purged.
- `tests/test_presentation.py`: a rank-and-lookup table carries metric values and ranks as numbers, so the window can sort them.
- `tests/test_demo_smoke.py`: guided stories come from `storefront`. The four-quarter story presents four distinct trace headers and evidence items, with the Sep 30, 2024 quarter at 65585000000. The filing-change story presents MD&A and Risk Factors as changed. The `.streamlit/secrets.toml.example` settings test went, because `test_render_env_*` covers the hosted settings.
- Streamlit-only behaviour (widget keys, autoscroll, sidebar state, Altair encodings) went with the app. The web unit tests and the browser check cover the window's own.
- `tests/test_deploy_config.py` adds two guards: the deploy notes have no legacy hosting section, and the lockfile and repo root hold no Streamlit, Altair, pandas, pyarrow, `.streamlit/`, or `requirements.txt`.

`prd.md` notes ADR 0006 under the Solution, strikes story 34 and marks it superseded, and annotates story 52, the primary seam, and the UI decision. The original text is kept. `docs/design.md` replaces the Streamlit audience layer with the Next.js window and the FastAPI seam, and links ADR 0006.

The API image shrank from 981 MB to 413 MB on disk (216 MB to 88.3 MB compressed). `scripts/smoke_api_image.py --image` passed against the new image.

