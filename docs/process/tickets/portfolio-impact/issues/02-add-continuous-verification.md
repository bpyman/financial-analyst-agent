# 02 — Add continuous verification

**What to build:** Every push and pull request shows that the offline suite, gold rehearsal, linter, and type checker pass. A recruiter or engineer can see a green check without cloning.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] Automated checks run pytest (including gold), ruff, and mypy on push and pull request.
- [x] A status badge is visible from the repository storefront.
- [x] Failures block merging rather than remaining a local-only ritual.

## Answer

`.github/workflows/ci.yml` runs ruff, mypy, pytest, and gold on push to `master` and on pull requests. The README badge points at that workflow. The suite is green locally (358 passed; ruff and mypy clean). The badge stays pending until this branch is pushed.

## Comments

- Agent: workflow is in the repo; first green check needs a push/PR.
