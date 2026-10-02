This is a portfolio project with no deadline. Do not time-box or drop work.

## Agent skills

### Issue tracker

The product PRD is `docs/process/prd.md`. Tickets live under `docs/process/tickets/<feature>/issues/`. See `docs/process/agents/issue-tracker.md`. How the agent workflow fits together: `docs/process/README.md`.

### Triage labels

Default role strings: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/process/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/process/agents/domain.md`.

### Snapshot membership

When ranking includes a fund, SPAC, BDC, note, or other non-operating listing, add its CIK to `src/financial_analyst_agent/data/ineligible_issuers.json` per `docs/adr/0001-snapshot-membership.md`.


