/**
 * The GitHub social preview (`capture-portfolio.ts`): the landing page's headline on
 * the left, the window's own fact card on the right. Pure, so the unit tests pin it;
 * the capture script supplies the headline, the card screenshot, and the fonts.
 */

export const SOCIAL_SIZE = { width: 1280, height: 640 } as const;

export interface SocialCard {
  /** The landing headline's first sentence, in full-strength text. */
  lead: string;
  /** The rest of the headline, in the muted colour the landing page gives it. */
  muted: string;
  /** Short facts shown as pills under the headline. */
  chips: string[];
  /** Where the project lives, printed at the bottom left. */
  repo: string;
  /** The fact card as a PNG data URI, captured at 2x. */
  card: string;
  /** Geist Sans and Geist Mono as woff2 data URIs, so the page needs no network. */
  fonts: { sans: string; mono: string };
}

const TREND_ICON =
  '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2.4" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg>';

function escape(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** A self-contained page that renders the preview at exactly `SOCIAL_SIZE`. */
export function socialCardHtml(card: SocialCard): string {
  const { width, height } = SOCIAL_SIZE;
  const chips = card.chips
    .map((chip, index) => `<span class="pill">${index === 0 ? '<span class="dot"></span>' : ""}${escape(chip)}</span>`)
    .join("");
  return `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:Geist;src:url(${card.fonts.sans}) format("woff2");font-weight:100 900}
@font-face{font-family:GeistMono;src:url(${card.fonts.mono}) format("woff2");font-weight:100 900}
*{box-sizing:border-box;margin:0}
html,body{width:${width}px;height:${height}px;overflow:hidden}
body{position:relative;font-family:Geist,sans-serif;color:#e8eaed;background:#07080a;
  background-image:linear-gradient(rgb(255 255 255/.035) 1px,transparent 1px),linear-gradient(90deg,rgb(255 255 255/.035) 1px,transparent 1px);
  background-size:32px 32px}
.glow{position:absolute;width:520px;height:420px;right:40px;top:120px;border-radius:50%;filter:blur(90px);background:rgb(59 130 246/.28)}
.brand{position:absolute;left:72px;top:64px;display:flex;align-items:center;gap:12px;font-weight:600;font-size:20px}
.logo{width:40px;height:40px;border-radius:10px;border:1px solid #2d323b;background:#14171c;display:grid;place-items:center}
h1{position:absolute;left:72px;top:170px;width:520px;font-size:56px;font-weight:650;letter-spacing:-.035em;line-height:1.02}
h1 span{color:#8a93a0}
.chips{position:absolute;left:72px;top:452px;width:600px;display:flex;gap:10px}
.pill{display:inline-flex;align-items:center;gap:8px;white-space:nowrap;border:1px solid #2d323b;background:#0e1014;border-radius:999px;padding:7px 14px;font-size:15px;color:#c5cad3}
.dot{width:8px;height:8px;border-radius:50%;background:#34d399}
.card{position:absolute;width:760px;right:-170px;top:128px;border-radius:16px;border:1px solid #2d323b;
  box-shadow:0 30px 80px rgb(0 0 0/.6),0 0 0 1px rgb(255 255 255/.03);transform:perspective(1600px) rotateY(-8deg) rotateX(2deg)}
.repo{position:absolute;left:72px;bottom:48px;font-family:GeistMono,monospace;font-size:15px;color:#69717e}
</style></head><body>
<div class="glow"></div>
<div class="brand"><div class="logo">${TREND_ICON}</div>Financial analyst agent</div>
<h1>${escape(card.lead)}<br><span>${escape(card.muted)}</span></h1>
<div class="chips">${chips}</div>
<img class="card" src="${card.card}" alt="">
<div class="repo">${escape(card.repo)}</div>
</body></html>`;
}
