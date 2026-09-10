# 03 — Make public sessions safe by default

**What to build:** A stranger can use a hosted copy of the agent without seeing another visitor's conversation thread, without sharing secrets, and without burning unbounded provider spend. Guided demo data is the default; live SEC access is optional, quota-guarded, and honest about what it is.

**Blocked by:** 02 — Add continuous verification.

**Status:** resolved

- [x] Each visitor gets an isolated conversation thread that expires and is cleaned up.
- [x] The default public mode uses recorded adapters and does not require visitor keys.
- [x] Live SEC, if offered, is quota-capped, caches provider responses, sanitizes errors, and keeps secrets server-side.
- [x] The universe snapshot's freeze date is visible, with a staleness warning when it is old.

## Answer

`new_thread_id()` replaces the shared `"local"` thread. Threads expire (`THREAD_TTL_SECONDS`) and `LocalThreadStore.purge_expired` deletes them. `PUBLIC_DEMO=true` forces recorded adapters. Live SEC is wrapped in `CachingSECDataSource` with per-thread turn and request quotas. Unexpected errors show a generic message. Snapshot freeze date and staleness copy come from `snapshot_status`. Hosted proof of isolation is ticket 06.

## Comments

- Agent: settings live in `.env.example` and `.streamlit/secrets.toml.example`.
