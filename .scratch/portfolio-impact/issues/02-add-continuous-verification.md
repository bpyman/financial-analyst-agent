# 02 — Add continuous verification

**What to build:** Every push and pull request shows that the offline suite, gold rehearsal, linter, and type checker pass. A recruiter or engineer can see a green check without cloning.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Automated checks run pytest (including gold), ruff, and mypy on push and pull request.
- [ ] A status badge is visible from the repository storefront.
- [ ] Failures block merging rather than remaining a local-only ritual.
