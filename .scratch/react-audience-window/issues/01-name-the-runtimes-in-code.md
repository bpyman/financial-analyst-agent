# 01 — Name the recorded and live runtimes in code

**What to build:** Code and config speak the glossary. A `Runtime` knows whether it is the **recorded runtime** or the **live runtime**, so anything holding one can ask. The builders a reader meets carry the glossary names: the runtime builder chosen by a recorded/live flag, and the recorded runtime's own builder. `APP_MODE=recorded` selects the recorded runtime, and `APP_MODE=fixture` keeps working as a deprecated alias so existing `.env` files and deploy notes do not break. Test fixtures and data files keep "fixture": in tests it is testing vocabulary, not the domain term.

This is the prefactor the runtime-binding ticket needs. Behaviour does not change.

Spec: ADR 0006 ("Glossary words in code and config"), `CONTEXT.md` (Recorded runtime, Live runtime).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] A built runtime reports which of the two runtimes it is
- [ ] The kill-switch and fixture names are gone from the application's public builders; every caller (both windows, MCP, evaluation, tests) uses the new names
- [ ] `APP_MODE` accepts `recorded` and `live`; `fixture` still selects the recorded runtime
- [ ] `.env.example` and settings docs say `recorded`
- [ ] pytest, ruff, and mypy pass
