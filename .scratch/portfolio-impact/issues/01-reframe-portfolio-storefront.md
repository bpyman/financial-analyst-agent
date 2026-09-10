# 01 — Reframe the portfolio storefront

**What to build:** A visitor who opens the repository in sixty seconds understands what the agent does, why it is trustworthy, and that it is a finished portfolio product rather than an interview homework dump. The interview origin stays available but below the fold. Architecture docs describe the shipped conversation thread and patchable analysis spec as current, not next.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] The public description leads with an evidence-first tagline and three differentiators: SEC quarterly facts, constrained planning, and answers the model cannot rewrite.
- [x] GitHub metadata, package description, and license no longer present the project as a POC.
- [x] Historical interview material is archived and linked, not the first thing a recruiter sees.
- [x] Design docs match the shipped stateful analysis graph.

## Answer

README, `pyproject.toml`, MIT `LICENSE`, and GitHub description/topics now lead with the evidence-first product, not a POC. Interview notes moved to `docs/archive/interview/`. `docs/design.md` documents the conversation seam and patchable analysis spec as current architecture. Homepage URL waits on ticket 06.

## Comments

- Agent: implemented on `cursor/portfolio-impact-tickets`; GitHub description updated via `gh repo edit`.
