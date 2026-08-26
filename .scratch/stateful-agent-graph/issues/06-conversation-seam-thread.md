# 06 — Conversation seam on a persisted thread

**Spec:** 01 — Stateful analysis graph

**What to build:** The new public entry point: a thread identifier, an analyst message, and a runtime in, one typed conversation turn out. Each **conversation thread** persists to a durable local store keyed by its identifier, so asking a second question against the same thread sees what came before, asking against a different identifier starts clean, and neither thread can read the other's state. The store must be swappable for a server-backed one later without touching this seam, and no database server is required to run the app.

Thread state holds the messages and the last completed result. Run state — whatever a single turn computes on its way to an answer — is not carried between turns. The application seam survives as a thin wrapper that opens an ephemeral single-message thread and returns the same result shape, so it stays the regression net for the whole migration.

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] The conversation seam accepts a thread identifier and an analyst message and returns a typed conversation turn
- [ ] Thread state round-trips: a second call with the same identifier sees the prior turn, a different identifier starts clean
- [ ] Thread state survives a process restart, with no database server required
- [ ] The application seam is a wrapper over an ephemeral thread and its tests pass with no assertion changes
- [ ] Run state is not carried between turns
- [ ] Tests exercise persistence against a temporary store rather than mocking it
