"""The stateful analysis graph (ADR 0005).

- ``turn_graph``: the parent graph, one conversation turn as fixed typed steps,
  and ``run_analysis``, which runs it on a thread's checkpoint.
- ``structured``: the structured-analysis subgraph (tasks → merge → history → notes).
- ``state``: the typed run state, requests, and the held clarification.
- ``clarify``: reading the analyst's reply to an open clarification.
- ``checkpointer``: the thread-record checkpointer that lets a clarification resume.
- ``analysis_spec`` and ``spec_turn``: the spec, its patches, resolution, and tasks.

Importing the package loads none of these, so modules that only need the spec
types (``analysis_spec``) do not pull in LangGraph or the workflows.
"""
