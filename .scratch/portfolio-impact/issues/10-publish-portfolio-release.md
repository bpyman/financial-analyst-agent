# 10 — Publish the portfolio release

**What to build:** The public project looks finished: screenshots, a short GIF or recording, social preview, hosted demo link, evaluation numbers, and copy a recruiter can scan. A follow-up LinkedIn post can point at the live product rather than a local clone.

**Blocked by:** 01 — Reframe the portfolio storefront; 06 — Deploy the guarded public demo; 07 — Publish an evaluation and operability scorecard; 09 — Complete the flagship filing-change workflow.

**Status:** ready-for-human

- [ ] README shows a hosted demo link, a 30–60 second visual, two screenshots (multi-quarter comparison and exact filing provenance), architecture at a glance, evaluation results, setup, and honest limitations.
- [ ] GitHub social preview uses a still from the demo.
- [ ] A 45–60 second clip exists: one-click comparison, a follow-up that extends the analysis spec, a chart, then click-through to exact SEC evidence.
- [x] LinkedIn-ready copy is written from the finished storefront, not from interview framing.

## Answer

Storefront, architecture, evaluation numbers (8/8), setup, and limitations are in README. LinkedIn draft is [`docs/portfolio/release.md`](../../../docs/portfolio/release.md). GIF, screenshots, social preview, and the live demo link wait on ticket 06's public URL.

## Comments

- Agent: do not fake a hosted URL. After Streamlit Cloud is live, capture the clip and stills listed in the release doc.
