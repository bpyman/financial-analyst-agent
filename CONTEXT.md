# Financial analyst agent

A demo agent that looks up reported quarterly facts for operating companies, ranks snapshot members from a dated freeze, and answers qualitative questions without inventing numbers.

## Language

**Universe snapshot**:
A dated freeze of US exchange-listed common shares of operating companies. Ranking reads this freeze; it does not rescreen the market. Lookup of a quarterly fact does not require freeze presence. Lookup of a snapshot metric (`market_cap`) does. News does not use it.
_Avoid_: live screener, universe, catalog

**Snapshot member**:
An operating company whose common share is present in this universe snapshot.
_Avoid_: SEC filer, listed company, issuer

**Operating company**:
A company that runs a business, as opposed to a shell, SPAC, fund, BDC, or other financing vehicle.
_Avoid_: issuer (unqualified), name, entity

**Common share**:
The ordinary equity listing of an operating company, not a preferred, unit, warrant, right, or listed note.
_Avoid_: security, ticker, listing (unqualified)

**Ineligible issuer**:
An operating-company lookalike identified by CIK after security type and industry are not enough to tell it apart. It is not a snapshot member and cannot be looked up or compared.
_Avoid_: blocklist entry, banned ticker

**Quarterly fact**:
A directly reported standalone-quarter amount from a 10-Q, with provenance.
_Avoid_: TTM, derived quarter, restatement

**Ambiguous metric**:
A user metric phrase that matches more than one name in the closed catalog.
_Avoid_: metric collision, unknown metric

**Unknown metric**:
A user metric phrase that names nothing in the closed catalog.
_Avoid_: ambiguous metric

**Conversation thread**:
One analyst investigation, identified and persisted. It carries the analysis spec, any pending clarification, the last result, and evidence references, and is bound to one runtime for its whole life. Threads do not share state.
_Avoid_: session, chat, conversation history, memory

**Recorded runtime**:
The provider set that replays captured SEC, news, and model responses. Orchestration and presentation are the same as live; only the providers differ. A thread started on it never takes a live turn.
_Avoid_: kill-switch, fixture mode, guided demo data, cassette

**Live runtime**:
The provider set that calls SEC EDGAR, the news search, and the model provider. A thread started on it never takes a recorded turn.
_Avoid_: production mode, real mode

**Analysis spec**:
The typed, resolved statement of the analyst's current quantitative question: companies or constituents, closed-catalog metrics, period selection, operations, and requested presentation. Resolved means CIKs and catalog slugs, so it can execute. It is the thing a follow-up edits.
_Avoid_: query, plan, intent, request

**Spec patch**:
The model's proposed edit to an analysis spec — additions, removals, replacements, and whether this turn extends or replaces the current analysis. Deterministic code resolves and validates it; a patch is never executed as given.
_Avoid_: plan, tool call, spec (unqualified)

**Pending clarification**:
An analysis spec held on a thread, awaiting the analyst's answer to one open question. Nothing has been fetched. Answering resumes it; asking something unrelated discards it.
_Avoid_: clarify pane, pending plan, interrupt

**Exploratory research**:
A labelled, cited, read-only answer for questions that no analysis spec expresses. It cannot produce reported facts, structured rows, or computed values.
_Avoid_: analysis, essay, explain
