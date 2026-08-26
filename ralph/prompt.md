# ISSUES

Read `prd.md`, `progress.txt`, and `CONTEXT.md`. Tracker conventions live in `docs/agents/issue-tracker.md`. An issue **index** (path, status, blockers) is provided above. Open the chosen ticket file on disk; do not expect full bodies in this prompt.

A ticket is **actionable** when all of these hold:

- `Status:` is `ready-for-agent` (a missing Status counts as ready-for-agent when the file is still in `issues/`, not `issues/done/`)
- it is on the **frontier**: every ticket in `Blocked by:` is `Status: resolved` or lives under `issues/done/` — confirm on disk if the index is ambiguous
- it is an implementation ticket (`**What to build:**` is present). A parent spec (user stories / implementation decisions, no What to build) stays put while numbered implementation tickets exist

Among the frontier, lowest number in that feature wins, then the priority order below.

If nothing is actionable, output <promise>NO MORE TASKS</promise> and stop.

# TASK SELECTION

Pick one ticket, in this order:

1. Critical bugfixes
2. Development infrastructure (tests, types, seams the next tracer needs)
3. Tracer bullets — a thin vertical slice through every layer, demoable on its own
4. Polish and quick wins
5. Refactors

# EXPLORATION

Read the chosen ticket, any spec it names, `CONTEXT.md`, and the ADRs it cites. Then the code. Name things with the glossary in `CONTEXT.md`.

# IMPLEMENTATION

Follow the TDD skill: red, then green, at the seams the ticket names. One ticket only.

# FEEDBACK LOOPS

Before committing, from the repo root:

- `uv run pytest`
- `uv run ruff check src tests`
- `uv run mypy`

All three must pass. Default tests stay offline (`pytest` already excludes `network`).

# COMMIT

Commit this ticket's work. The message says why, then:

1. Key decisions
2. Files changed
3. Blockers or notes for the next iteration

# CLOSE THE TICKET

Append a dated entry to `progress.txt`: ticket path, key decisions, files changed, blockers / next.

If the ticket is done: set `Status: resolved` and append `## Answer` with what shipped.

If the ticket is not done: append `## Comments` with what changed and what remains; leave `Status: ready-for-agent`.

# FINAL RULES

Work a single ticket.
