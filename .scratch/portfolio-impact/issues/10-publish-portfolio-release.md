# 10 — Publish the portfolio release

**What to build:** The public project looks finished: screenshots, a short GIF or recording, social preview, hosted demo link, evaluation numbers, and copy a recruiter can scan. A follow-up LinkedIn post can point at the live product rather than a local clone.

**Blocked by:** 01 — Reframe the portfolio storefront; 06 — Deploy the guarded public demo; 07 — Publish an evaluation and operability scorecard; 09 — Complete the flagship filing-change workflow.

**Status:** ready-for-human

- [x] README shows a hosted demo link, a 30–60 second visual, two screenshots (multi-quarter comparison and exact filing provenance), architecture at a glance, evaluation results, setup, and honest limitations.
- [x] GitHub social preview uses a still from the demo.
- [ ] A 45–60 second clip exists: one-click comparison, a follow-up that extends the analysis spec, a chart, then click-through to exact SEC evidence.
- [x] LinkedIn-ready copy is written from the finished storefront, not from interview framing.

## Answer

README Try-it now has the hosted URL, a looping GIF, the four-quarter chart still, and the evidence-inspector still. Scorecard copy is **9/9**. LinkedIn draft is [`docs/portfolio/release.md`](../../../docs/portfolio/release.md).

Stills and GIF were captured from https://financial-analyst-agent-project.streamlit.app:

- [`docs/portfolio/images/demo-walkthrough.gif`](../../../docs/portfolio/images/demo-walkthrough.gif)
- [`docs/portfolio/images/compare-four-quarters.png`](../../../docs/portfolio/images/compare-four-quarters.png)
- [`docs/portfolio/images/inspect-exact-source.png`](../../../docs/portfolio/images/inspect-exact-source.png)
- [`docs/portfolio/images/social-preview.png`](../../../docs/portfolio/images/social-preview.png) (1280×640)

The GIF is a three-beat walkthrough (guided stories → comparison chart → Open filing), not a 45–60s screen recording. Apple 10-Q revenue is now in the fixture tape, so the remaining clip can include `add Apple`.

GitHub social preview: uploaded in Settings from `docs/portfolio/images/social-preview.png`.

## Comments

- Agent: do not fake a hosted URL. After Streamlit Cloud is live, capture the clip and stills listed in the release doc.
- Agent: captured live-demo stills and GIF; social preview still needs a Settings upload.
- Human: uploaded `docs/portfolio/images/social-preview.png` in GitHub Settings → Social preview.
