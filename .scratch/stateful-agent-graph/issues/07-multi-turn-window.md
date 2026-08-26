# 07 — Multi-turn audience window

**Spec:** 01 — Stateful analysis graph

**What to build:** An analyst asks a second question without retyping the first. The window owns a thread identifier, sends each message to the conversation seam, and shows the exchange as a history rather than replacing one answer with the next — so a follow-up reads as a continuation, and a browser refresh or an app restart returns to the same thread instead of an empty page.

Everything the window already does stays: the runtime badge, the fixture warning, tool traces with inputs and provenance, tables, fact cards, citations, clarify, and refusal. The fixture kill-switch keeps swapping adapters only, so recorded and live runs share one topology. Formatting stays in the presentation mapping — the window gains no financial logic, and new result fields are covered by presentation tests rather than by booting the UI.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] The window holds a thread identifier and sends every message to the conversation seam
- [ ] Prior turns stay visible as a history, and a refresh or restart returns to the same thread
- [ ] Runtime badge, fixture warning, tool traces, tables, fact cards, citations, clarify, and refusal all still render
- [ ] The kill-switch still swaps adapters only
- [ ] New result fields are asserted in presentation tests, not by rendering the app
