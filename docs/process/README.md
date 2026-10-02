# How this was built

Onfile was built largely by coding agents working under my direction, between 17 August and 2 October 2026. This folder keeps the working files that drove that process. Nothing in the app reads them.

## How the pieces fit

1. **PRD.** [`prd.md`](prd.md) states the product: who it is for, user stories, the closed intents, and what is out of scope. It is the spec a ticket is checked against.
2. **ADRs.** [`docs/adr/`](../adr/) records each decision that constrains the code, with the options rejected. When a decision changes, the ADR is revised in place and says what it supersedes. ADR 0007, for example, revises ADR 0003's ban on derived quarters.
3. **Tickets.** [`tickets/<feature>/issues/NN-*.md`](tickets/) breaks a feature into vertical slices, each with acceptance criteria, a `Blocked by` line and a `Status`. The conventions are in [`agents/issue-tracker.md`](agents/issue-tracker.md) and [`agents/triage-labels.md`](agents/triage-labels.md).
4. **Ralph loop and agent sessions.** [`ralph/`](ralph/) runs an agent on the next open, unblocked ticket: `once.sh` for one ticket, `afk.sh` to repeat until none are left. [`ralph/prompt.md`](ralph/prompt.md) tells the agent to read the PRD, progress log and glossary, implement one ticket, run the checks, commit, and append to [`progress.txt`](progress.txt). Larger or open-ended work ran in interactive Claude Code sessions instead: local ones, and cloud ones on `claude/*` branches.
5. **Pull requests.** Work lands on `master` through PRs. Of the 50 merged PRs, 47 came from cloud sessions' `claude/...` branches, one from a Cursor branch, and two from local branches.
6. **CI.** [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs on every push and PR: ruff, strict mypy, pytest and the gold prompts; a Docker image build with a smoke test; and in `web/`, lint, unit tests, a build, a type check and a Playwright browser check against the recorded API. A deploy job fires only for the commit at the tip of `master` after every check passes.
7. **Human review and merge.** I merged all 50 PRs. How I review them is in my account below.

## Who wrote the commits

On `master` at 2 October 2026 there are 335 commits:

| Author | Commits | Of which |
| --- | ---: | --- |
| Claude (cloud sessions) | 194 | 12 merge commits |
| Blake Pyman (`Blake Pyman` and `bpyman`) | 141 | 39 PR merge commits. Of the other 102: 77 carry a `Co-authored-by: Cursor` trailer (the Ralph loop and Cursor sessions), 24 a `Co-Authored-By: Claude` trailer (local Claude Code sessions), and 1 neither. |

So nearly every change on `master` was written by an agent. My part is in the decisions, the reviews and the merges.

## What I decided, how I caught mistakes, and how I review

<!-- BLAKE: your own account goes here, in your words. Not written by an agent. -->

_To be written by Blake._
