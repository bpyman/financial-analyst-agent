# 15 — Exploratory research lane

**Spec:** 01 — Stateful analysis graph

**What to build:** A useful answer to a question no analysis spec expresses, without pretending it is an analysis. Such a question routes to an **exploratory research** subgraph whose output is visibly labelled as research rather than reported facts, and cites the evidence it drew on so a draft can be checked.

The lane is deliberately fenced. It is read-only and restricted to approved capabilities — search stays the constrained news wrapper, with no extract, crawl, map, second vendor, or open web browsing. It cannot emit structured financial rows, and it cannot introduce a numeral that its evidence does not contain, so the reliable table path stays reliable no matter what this lane returns. Routing into it is a workflow selection from the closed set; it is not the model deciding to go off-piste.

**Blocked by:** 06

**Status:** resolved

- [x] A question no analysis spec expresses routes to the exploratory lane
- [x] Its output is labelled as research, distinct from reported facts, and carries citations
- [x] It cannot emit structured financial rows
- [x] It cannot introduce numerals absent from its evidence
- [x] It stays read-only and within the constrained news wrapper
- [x] Routing is a selection from the closed workflow set

## Answer

Shipped `Intent.EXPLORATORY_RESEARCH` as a seventh closed workflow. The parent graph dispatches to a one-node exploratory subgraph that searches via the constrained news wrapper, numeral-locks the essay against hit JSON, banners `exploratory-research` (not `model-analysis`), returns citations, and never emits table rows. Empty or failed news refuses rather than falling back to training data. The conversation seam treats it as qualitative (clears the analysis spec). Planner schema and DemoCompleter recognize theme/coverage research questions; fixture news/essay recordings cover the Hormuz research prompt.
