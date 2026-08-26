The 20 August 2026 interview is done and went well. There is no deadline. Continue this as a portfolio project; do not time-box or drop work for Thursday.

## Agent skills

### Issue tracker

The product PRD is `prd.md` at the repo root. Tickets live under `.scratch/<feature>/issues/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default role strings: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Snapshot membership

When ranking includes a fund, SPAC, BDC, note, or other non-operating listing, add its CIK to `src/financial_analyst_agent/data/ineligible_issuers.json` per `docs/adr/0001-snapshot-membership.md`.


