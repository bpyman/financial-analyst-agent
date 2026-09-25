# 13 — Old Streamlit links land on a "moved" page

**What to build:** Links to the old Community Cloud URL keep working after cutover. A `streamlit-redirect` branch holds a single Streamlit page saying the demo has moved, with a button to the new URL (read from app secrets, with a sensible default), plus its own minimal requirements. The deploy notes tell Blake how to repoint the Community Cloud app at that branch.

Spec: ADR 0006 (Migration).

**Blocked by:** 09

**Status:** ready-for-agent

- [ ] The branch exists, holds only the moved page, its requirements, and a README
- [ ] The page runs locally with only its own requirements installed
- [ ] The deploy notes carry the repoint steps
