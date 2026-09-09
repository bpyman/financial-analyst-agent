# 03 — Make public sessions safe by default

**What to build:** A stranger can use a hosted copy of the agent without seeing another visitor's conversation thread, without sharing secrets, and without burning unbounded provider spend. Guided demo data is the default; live SEC access is optional, quota-guarded, and honest about what it is.

**Blocked by:** 02 — Add continuous verification.

**Status:** ready-for-agent

- [ ] Each visitor gets an isolated conversation thread that expires and is cleaned up.
- [ ] The default public mode uses recorded adapters and does not require visitor keys.
- [ ] Live SEC, if offered, is quota-capped, caches provider responses, sanitizes errors, and keeps secrets server-side.
- [ ] The universe snapshot's freeze date is visible, with a staleness warning when it is old.
