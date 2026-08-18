# ISSUES

Read PRD.md and progress.txt.
Local issue files from 'issues/' are provided at start of context.  Parse them to understand the open issues.
If all ready-for-agent tasks are complete, output <promise>NO MORE TASKS</promise>.

# TASK SELECTION

Pick the next task.  Prioritize tasks in this order:

1. Critical bugfixes
2. Development infrastructure (required tests, types, dev scripts)
3. Tracer bullets for new features

Tracer bullets are small slices of functionality that go through all layers of the system, allowing you to test and validate your approach early.  This helps in identifying potential issues and ensure that the overall architecture is sound before investing significant time in development.

TL;DR - build a tiny, end-to-end slice of the feature first, then expand it out.

4. Polish and quick wins
5. Refactors

# EXPLORATION

Explore the repo.

# IMPLEMENTATION

Use /tdd to complete the task.

# FEEDBACK LOOPS

Before committing, run the feedback loops:

- `npm run test` to run the tests
- `npm run typecheck` to run the type checker

# COMMIT

Make a git commit.  The commit message must include:

1. Include key decisions made
2. Include files changed
3. Blockers or notes for next interation

# THE ISSUE

After completing each task, append to progress.txt:
- Task completed and PRD item reference
- Key decisions made and reasoning
- Files changed
- Any blockers or notes for next iteration
Keep entries concise. This file helps future iterations skip exploration.

If the task is complete, move the issue file to `issues/done/`.

If the task is not complete, add a note to the issue file with what was done.

# FINAL RULES

ONLY WORK ON A SINGLE TASK.