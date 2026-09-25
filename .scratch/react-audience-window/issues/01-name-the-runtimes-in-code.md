# 01 — Name the recorded and live runtimes in code

**What to build:** Code and config speak the glossary. A `Runtime` knows whether it is the **recorded runtime** or the **live runtime**, so anything holding one can ask. The builders a reader meets carry the glossary names: the runtime builder chosen by a recorded/live flag, and the recorded runtime's own builder. `APP_MODE=recorded` selects the recorded runtime, and `APP_MODE=fixture` keeps working as a deprecated alias so existing `.env` files and deploy notes do not break. Test fixtures and data files keep "fixture": in tests it is testing vocabulary, not the domain term.

This is the prefactor the runtime-binding ticket needs. Behaviour does not change.

Spec: ADR 0006 ("Glossary words in code and config"), `CONTEXT.md` (Recorded runtime, Live runtime).

**Blocked by:** None — can start immediately

**Status:** resolved

- [x] A built runtime reports which of the two runtimes it is
- [x] The kill-switch and fixture names are gone from the application's public builders; every caller (both windows, MCP, evaluation, tests) uses the new names
- [x] `APP_MODE` accepts `recorded` and `live`; `fixture` still selects the recorded runtime
- [x] `.env.example` and settings docs say `recorded`
- [x] pytest, ruff, and mypy pass

## Answer

Shipped 2026-09-25.

- `RuntimeKind` (`recorded` / `live`) lives in `contracts.py` and is re-exported from `turn`. `Runtime.kind` defaults to recorded, since a runtime assembled from test doubles replays canned answers; `recorded_runtime()` sets `RECORDED`, `live_runtime()` sets `LIVE`, and the two live integration tests set `LIVE` on their hand-built runtimes.
- Builders: `fixture_runtime()` is now `recorded_runtime()`; `runtime_for_kill_switch(enabled=...)` is now `runtime_for(kind, *, settings, budget)`. A locked public demo still builds the recorded runtime when live is asked for, and the returned `Runtime.kind` says so. That is what ticket 02 needs to report the coercion. `build_runtime()` keeps its name and follows `APP_MODE`.
- `AppMode` is `LIVE` / `RECORDED`. `AppMode._missing_` accepts `fixture` (any case) as a deprecated alias for `recorded` and logs a warning; unknown values still fail validation.
- Callers updated: Streamlit (`recorded` locals, `history_recorded` session key, `RECORDED_BANNER` directly; the `KILL_SWITCH_BANNER` alias is gone), the API, evaluation, and every test. MCP already used `build_runtime`.
- Config and docs say `recorded`: `.env.example`, `.streamlit/secrets.toml.example`, README local-run steps, `docs/deploy.md`, `docs/design.md`, and ADR 0006's seam list.
- Left alone on purpose: the data file `fixture_universe_snapshot.json` (`FIXTURE_UNIVERSE_SNAPSHOT_PATH`), the recorded providers `FixtureNewsSearch` / `FixtureEssayCompleter`, `FIXTURE_NEWS_QUERY`, the checked-in `docs/evaluation/scorecard.*` (regenerating it changes its timestamps; the generator now says "recorded runtime"), and the PRD's historical user stories. The Streamlit badge still reads "Guided demo" / "Live SEC", because on-screen copy belongs to the window tickets and Streamlit is deleted at cutover.
- `tests/test_kill_switch.py` became `tests/test_runtime_choice.py`, covering the runtime kinds, locked-demo coercion, and the `APP_MODE` alias.
