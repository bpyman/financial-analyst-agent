## Agent skills

### Issue tracker

The product PRD is `prd.md` at the repo root. Tickets live under `.scratch/<feature>/issues/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default role strings: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Snapshot membership

When ranking includes a fund, SPAC, BDC, note, or other non-operating listing, add its CIK to `src/financial_analyst_agent/data/ineligible_issuers.json` per `docs/adr/0001-snapshot-membership.md`.


## Code Review Rules

Review changes as a pragmatic senior engineer preparing a reliable demonstration, not as an exhaustive hardening or adversarial security audit.

### Primary objectives

1. Determine whether the ticket's acceptance criteria are satisfied.
2. Identify material defects that should genuinely prevent ticket closure.
3. Help the project progress without expanding the ticket's scope.

### Review scope

* Review the current ticket's changes and directly connected code only.
* Treat the ticket, PRD, documented assumptions, and supported interfaces as the source of truth.
* Check the primary workflow and a small number of realistic failure paths.
* Run the smallest relevant set of tests or checks when useful.
* Do not turn a ticket review into a general repository audit.

### Finding threshold

Report a bug only when all of the following are true:

* It violates an acceptance criterion, documented invariant, or supported behavior.
* It has a plausible trigger during the demo or normal intended use.
* It produces observable incorrect behavior.
* Its impact is meaningful enough to justify delaying ticket completion.
* The problem can be explained concretely and has a reasonably localized fix.

Valid findings include:

* Missing or incorrectly implemented acceptance criteria.
* Incorrect results, calculations, selections, transformations, or provenance.
* Crashes, hangs, or unusable behavior on normal inputs.
* Data loss, corruption, leakage, or material security problems.
* Integration mismatches that break a supported workflow.
* Regressions in previously working behavior.
* Missing error handling for common and reasonably expected failures.
* Missing tests only when the gap leaves a material behavior or demonstrated regression unprotected.

Do not report:

* Pathological malformed inputs that cannot normally reach the component.
* Extremely unlikely edge cases with negligible demo or user impact.
* Purely theoretical concurrency, scale, or performance concerns.
* Defense-in-depth opportunities when the existing boundary is adequate for the stated scope.
* Style, naming, formatting, minor duplication, or subjective design preferences.
* Refactoring or abstraction opportunities that do not correct a current defect.
* Additional validation or test permutations without a plausible failure they protect against.
* Unrelated pre-existing problems.
* Speculative concerns phrased only as something that "could" happen without a concrete trigger and outcome.
* Production-hardening work that is not required by the ticket or current project stage.

### Severity

Report only:

* **P0:** Catastrophic failure, severe security exposure, or unrecoverable data loss.
* **P1:** Breaks an acceptance criterion, primary workflow, demo path, or produces materially incorrect output.
* **P2:** A real defect on a plausible supported path that is important enough to fix before closing the ticket.

Do not report P3 issues or optional improvements as bugs.

Every P2 finding must explain why it is worth delaying ticket closure.

### Required evidence

For every finding, provide:

* Severity.
* File and relevant location.
* Concrete triggering input or execution path.
* Actual behavior.
* Expected behavior.
* Material impact.
* Smallest reasonable fix.

Do not report a finding if these points cannot be established with reasonable confidence.

### Output

Begin with exactly one verdict:

* **PASS:** The ticket is complete and has no material findings.
* **CHANGES REQUIRED:** One or more material findings should be fixed before closure.

List no more than five findings, ordered by severity and impact. If more exist, report only the five most consequential.

Do not include optional improvements, praise, summaries of the implementation, or a backlog of hardening ideas.

If there are no material findings, state:

> PASS: The ticket satisfies its acceptance criteria and no material defects were found.

Then stop.

### Stopping rule

Once the acceptance criteria are satisfied, relevant tests pass, and no P0-P2 findings remain, recommend closing the ticket.

After reported bugs are fixed, perform one focused regression review. Do not reopen previously reviewed areas or start another hardening cycle unless the fixes introduced new evidence of a material problem.
