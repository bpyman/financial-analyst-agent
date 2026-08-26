# 02 — Split the turn module into contracts and workflows

**Spec:** 01 — Stateful analysis graph

**What to build:** Nothing an analyst can see. The application seam currently holds the runtime ports, the result models, the closed intent and renderer enums, the metric constants, and all six workflow implementations in one module, and both the planner and the runtime import back into it. A graph package cannot sit above that without an import cycle. Separate the stable contracts (ports and `Runtime`, result and row models, enums, metric constants) from the workflow implementations, and keep the existing seam re-exporting every name it exports today so no caller — planner, runtime wiring, MCP server, presentation, or any test — changes an import. Behaviour, provenance, and every assertion stay byte-identical.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Runtime ports, result models, enums, and metric constants live in modules that carry no workflow logic
- [ ] The application seam re-exports its current public names, so no other module or test changes an import
- [ ] A new package can import the contracts without importing the workflow implementations
- [ ] The offline suite passes with no assertion changes, and strict type checking and lint stay clean
