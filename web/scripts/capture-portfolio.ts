import { spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContextOptions, type Locator, type Page } from "@playwright/test";
import { Analyst } from "../e2e/analyst";
import { findFfmpeg, gifArgs, mp4Args } from "./portfolio-media";
import { SOCIAL_SIZE, socialCardHtml } from "./social-card";

/**
 * Re-captures the README's portfolio media from the window (ADR 0006 cutover
 * criteria): the stills of compare four quarters, `add Apple`, and the exact 10-Q
 * source; a walkthrough of Eli Lilly, Pfizer and Merck revenue, then `show
 * year-over-year`, then the 10-Q source behind a Lilly value; the showcase answers
 * (Eli Lilly overtaking Pfizer, what changed in Microsoft's latest 10-Q) and the
 * social preview built from the first of them.
 *
 *   npm run build && npm run capture
 *
 * Runs against the recorded runtime in the default dark theme. Stills are taken on
 * a fresh thread at 2x; the walkthrough is recorded on another, then converted to
 * MP4 and GIF with ffmpeg (`$FFMPEG`, or `ffmpeg` on PATH).
 */

const OUT = process.env.PORTFOLIO_DIR ?? path.resolve(__dirname, "../../docs/portfolio/images");
const VIEWPORT = { width: 1280, height: 800 };
const STILL = { width: 1280, height: 1000 };
// Narrow enough that the chart, drawn at 2x and set 704 px wide on the card, keeps its text large.
const SOCIAL_WINDOW = { width: 700, height: 1000 };
// The card is read near 550 px wide in a feed: its chart's labels are drawn larger for it.
const SOCIAL_CHART_STYLE = `
  figure svg text.end-label { font-size: 21px !important; }
  figure svg .recharts-cartesian-axis-tick text { font-size: 14px !important; }
  figure header { font-size: 115%; }
  figure figcaption { display: none; }
`;
const REPO = "github.com/bpyman/onfile";
const CHIPS = ["Provenance on every number"];
/** The showcase questions, both answerable on the recorded runtime. */
const LILLY_VS_PFIZER = "Compare Eli Lilly and Pfizer revenue over the last eight quarters";
const MSFT_10Q_CHANGES = "What changed in Microsoft's latest 10-Q?";
const NVIDIA_OVERVIEW = "How is Nvidia doing?";
/** The walkthrough's question, before its `show year-over-year` follow-up. */
const PHARMA_REVENUE = "Compare Eli Lilly, Pfizer and Merck revenue over the last eight quarters";

const FILES = {
  landing: "guided-first-run.png",
  compare: "compare-four-quarters.png",
  inspect: "inspect-exact-source.png",
  lilly: "compare-lilly-pfizer.png",
  changes: "filing-changes.png",
  overview: "overview-trends.png",
  sorted: "sorted-ranking.png",
  social: "social-preview.png",
  mp4: "demo-walkthrough.mp4",
  gif: "demo-walkthrough.gif",
} as const;

const DARK: BrowserContextOptions = { viewport: VIEWPORT, colorScheme: "dark", reducedMotion: "no-preference" };

test("capture the portfolio stills and walkthrough", async ({ browser }) => {
  // Fail before driving the browser if the recording could not be converted.
  const ffmpeg = findFfmpeg(process.env, (command) => spawnSync(command, ["-version"]).status === 0);
  mkdirSync(OUT, { recursive: true });

  await captureStills(browser);
  await captureShowcase(browser);
  await captureSocial(browser);
  await captureWalkthrough(browser, ffmpeg);
});

async function captureStills(browser: Browser) {
  const context = await browser.newContext({ ...DARK, viewport: STILL, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const analyst = new Analyst(page);

  await analyst.open();
  await settle(page);
  await shoot(page, FILES.landing);

  await analyst.tell("Compare four quarters");
  await expect(analyst.charts()).toHaveCount(1);
  await frame(page, lastTurn(page));
  await shoot(page, FILES.compare);

  await analyst.ask("add Apple");
  await expect(analyst.charts()).toHaveCount(2);

  const inspector = await chooseEvidence(page, "Apple");
  await frame(page, inspector);
  await shoot(page, FILES.inspect);

  await context.close();
}

/** The showcase answers: a two-company trend with its table, and a 10-Q section diff. */
async function captureShowcase(browser: Browser) {
  const context = await browser.newContext({ ...DARK, viewport: STILL, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const analyst = new Analyst(page);

  await analyst.open();
  await analyst.ask(LILLY_VS_PFIZER);
  await expect(analyst.charts()).toHaveCount(1);
  await frame(page, lastTurn(page));
  await shoot(page, FILES.lilly);

  await analyst.startOver();
  await analyst.ask(MSFT_10Q_CHANGES);
  // The MD&A highlights, where Microsoft Cloud growth goes from 20% to 29%.
  const mdna = lastTurn(page)
    .getByRole("article", { name: /^Management's Discussion and Analysis/ })
    .filter({ hasText: "Microsoft Cloud revenue increased" });
  await expect(mdna).toBeVisible();
  await frame(page, mdna);
  await shoot(page, FILES.changes);

  // One company's overview: a sentence, then its recent quarters as small trends.
  await analyst.startOver();
  await analyst.ask(NVIDIA_OVERVIEW);
  await expect(lastTurn(page).getByRole("region", { name: "Recent quarters" }).getByRole("figure")).toHaveCount(2);
  await frame(page, lastTurn(page));
  await shoot(page, FILES.overview);

  // A ranking re-sorted by its R&D column, the chart's bars following the table.
  await analyst.startOver();
  await analyst.tell("Rank then inspect filings");
  await analyst.tables().last().getByRole("columnheader", { name: /Research and development/ }).getByRole("button").click();
  await expect(lastTurn(page).getByText(/^Ordered as the table:/)).toBeVisible();
  await frame(page, lastTurn(page));
  await shoot(page, FILES.sorted);

  await context.close();
}

/**
 * The social preview: the landing headline beside the Eli Lilly and Pfizer revenue
 * trend, where the lines cross, both taken from the window and composed by `social-card.ts`.
 */
async function captureSocial(browser: Browser) {
  // A narrower window, so the chart's labels stay legible at the card's size.
  const context = await browser.newContext({ ...DARK, viewport: SOCIAL_WINDOW, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const analyst = new Analyst(page);

  await analyst.open();
  const headline = page.getByRole("heading", { level: 1 });
  const muted = (await headline.locator("span").textContent())?.trim() ?? "";
  const lead = ((await headline.textContent()) ?? "").replace(muted, "").trim();

  await analyst.ask(LILLY_VS_PFIZER);
  const chart = analyst.charts().last();
  await expect(chart).toBeVisible();
  await page.addStyleTag({ content: SOCIAL_CHART_STYLE });
  await settle(page);
  await page.mouse.move(0, 0);
  const card = await chart.screenshot({ animations: "disabled" });
  await context.close();

  const composer = await browser.newContext({ viewport: SOCIAL_SIZE, deviceScaleFactor: 1 });
  const canvas = await composer.newPage();
  await canvas.setContent(
    socialCardHtml({ lead, muted, chips: CHIPS, repo: REPO, card: dataUri("image/png", card), fonts: geistFonts() }),
  );
  await settle(canvas);
  await canvas.screenshot({ path: path.join(OUT, FILES.social), animations: "disabled" });
  // The same card is the site's link preview (LinkedIn, X, Slack); see app/layout.tsx.
  copyFileSync(path.join(OUT, FILES.social), path.resolve(__dirname, "../public/social-preview.png"));
  await composer.close();
}

function dataUri(type: string, bytes: Buffer): string {
  return `data:${type};base64,${bytes.toString("base64")}`;
}

/** The window's own typefaces, from the `geist` package. */
function geistFonts(): { sans: string; mono: string } {
  const fonts = path.resolve(__dirname, "../node_modules/geist/dist/fonts");
  const woff2 = (file: string) => dataUri("font/woff2", readFileSync(path.join(fonts, file)));
  return { sans: woff2("geist-sans/Geist-Variable.woff2"), mono: woff2("geist-mono/GeistMono-Variable.woff2") };
}

async function captureWalkthrough(browser: Browser, ffmpeg: string) {
  const videoDir = test.info().outputPath("video");
  const context = await browser.newContext({ ...DARK, recordVideo: { dir: videoDir, size: VIEWPORT } });
  await context.addInitScript(showCursor);
  const recordingStarted = Date.now();
  const page = await context.newPage();
  const analyst = new Analyst(page);
  const cursor = new Cursor(page);

  await analyst.open();
  await settle(page);
  const startAt = (Date.now() - recordingStarted) / 1000;
  await cursor.moveTo(page.getByRole("textbox", { name: "Ask a question" }), 0.2);
  await page.waitForTimeout(1200);

  // A question in plain words: three companies' revenue as a trend with its table.
  await ask(page, analyst, cursor, PHARMA_REVENUE, 40);
  await centre(page, analyst.charts().last());
  await cursor.sweep(analyst.charts().last());
  await page.waitForTimeout(800);

  // A follow-up edits the analysis: the same three companies, as growth rates.
  await ask(page, analyst, cursor, "show year-over-year", 90);
  await centre(page, analyst.charts().last());
  await cursor.sweep(analyst.charts().last());
  await page.waitForTimeout(800);

  // The 10-Q source behind Eli Lilly's latest quarter: amount, accession, concept.
  const inspector = lastTurn(page).getByRole("region", { name: "Evidence inspector" });
  await smoothScrollTo(page, inspector);
  await page.waitForTimeout(700);
  await cursor.moveTo(inspector.getByRole("combobox", { name: "Evidence item" }));
  await page.waitForTimeout(300);
  await chooseEvidence(page, "Eli Lilly");
  await page.waitForTimeout(1000);
  for (const field of ["Exact amount", "Accession number", "Concept"]) {
    await cursor.moveTo(inspector.getByText(field, { exact: true }), 0.1);
    await page.waitForTimeout(900);
  }
  // Rest in the margin, so the last frames show every field uncovered.
  await page.mouse.move(VIEWPORT.width - 100, VIEWPORT.height / 2, { steps: 24 });
  await page.waitForTimeout(2200);

  const video = page.video();
  if (!video) throw new Error("the walkthrough context did not record a video");
  await context.close();
  const recording = await video.path();

  convert(ffmpeg, mp4Args(recording, path.join(OUT, FILES.mp4), { startAt }));
  convert(ffmpeg, gifArgs(recording, path.join(OUT, FILES.gif), { startAt, fps: 8, width: 880 }));
  rmSync(videoDir, { recursive: true, force: true });
}

/** Types `question` into the composer as a visitor would, sends it, and waits for the answer. */
async function ask(page: Page, analyst: Analyst, cursor: Cursor, question: string, delay: number) {
  const composer = page.getByRole("textbox", { name: "Ask a question" });
  await cursor.click(composer);
  await composer.pressSequentially(question, { delay });
  await page.waitForTimeout(500);
  const asked = await analyst.turnsUsed();
  await page.keyboard.press("Enter");
  await composer.blur();
  await analyst.waitForTurn(asked + 1);
  await page.waitForTimeout(1200);
}

function lastTurn(page: Page): Locator {
  return page.locator("[data-turn]:not([data-turn=pending])").last();
}

/** Picks `company`'s first standalone 10-Q fact in the last answer's evidence inspector. */
async function chooseEvidence(page: Page, company: string): Promise<Locator> {
  const inspector = lastTurn(page).getByRole("region", { name: "Evidence inspector" });
  const select = inspector.getByRole("combobox", { name: "Evidence item" });
  const labels = await select.locator("option").allTextContents();
  for (const [index, label] of labels.entries()) {
    if (!label.includes(company)) continue;
    await select.selectOption({ index });
    // Wait for the inspector to show this item before reading its selection rule.
    await expect(inspector.getByText(label.split(" · ").at(-1) ?? label, { exact: true })).toBeVisible();
    if ((await inspector.textContent())?.includes("Standalone 10-Q")) return inspector;
  }
  throw new Error(`no standalone 10-Q ${company} fact among: ${labels.join(" | ")}`);
}

async function shoot(page: Page, name: string) {
  await page.mouse.move(0, 0);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.screenshot({ path: path.join(OUT, name), animations: "disabled" });
}

/** Lets fonts, chart animations, and the answer's smooth scroll finish. */
async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(1200);
}

/** How far `target` sits below the sticky header and status line, less a small gap. */
async function offsetFromTop(target: Locator, gap = 16): Promise<number> {
  return target.evaluate((element, margin) => {
    let covered = 0;
    for (const node of document.body.querySelectorAll("*")) {
      const { position } = getComputedStyle(node);
      if (position !== "sticky" && position !== "fixed") continue;
      const box = node.getBoundingClientRect();
      // The header and the status line under it; not the composer fixed at the bottom.
      if (box.height > 0 && box.bottom < window.innerHeight / 3) covered = Math.max(covered, box.bottom);
    }
    return element.getBoundingClientRect().top - covered - margin;
  }, gap);
}

/** Waits out the window's own scroll to the new answer, then puts `target` at the top. */
async function frame(page: Page, target: Locator, gap?: number) {
  await settle(page);
  await bringToTop(page, target, gap);
  await settle(page);
}

/** Scrolls so `target` starts just under the sticky header. */
async function bringToTop(page: Page, target: Locator, gap?: number) {
  const distance = await offsetFromTop(target, gap);
  await page.evaluate((by) => window.scrollBy({ top: by, behavior: "instant" }), distance);
}

/**
 * Scrolls so `target` sits in the middle of what the sticky header and the composer
 * leave visible, or just under the header if it is taller than that.
 */
async function centre(page: Page, target: Locator) {
  const distance = await target.evaluate((element) => {
    let top = 0;
    let bottom = window.innerHeight;
    for (const node of document.body.querySelectorAll("*")) {
      const { position } = getComputedStyle(node);
      if (position !== "sticky" && position !== "fixed") continue;
      const box = node.getBoundingClientRect();
      if (box.height === 0) continue;
      // The header and status line above, the composer below.
      if (box.bottom < window.innerHeight / 3) top = Math.max(top, box.bottom);
      else if (box.top > (window.innerHeight * 2) / 3) bottom = Math.min(bottom, box.top);
    }
    const box = element.getBoundingClientRect();
    const room = bottom - top;
    const want = box.height < room ? top + (room - box.height) / 2 : top + 16;
    return box.top - want;
  });
  await scrollBy(page, distance);
}

async function smoothScrollTo(page: Page, target: Locator) {
  await scrollBy(page, await offsetFromTop(target));
}

async function scrollBy(page: Page, distance: number) {
  const steps = Math.max(1, Math.round(Math.abs(distance) / 24));
  for (let step = 0; step < steps; step += 1) {
    await page.mouse.wheel(0, distance / steps);
    await page.waitForTimeout(16);
  }
  await page.waitForTimeout(250);
}

function convert(ffmpeg: string, args: string[]) {
  const result = spawnSync(ffmpeg, ["-hide_banner", "-loglevel", "error", ...args], { stdio: "inherit" });
  if (result.status !== 0) throw new Error(`ffmpeg failed (${result.status}): ${args.join(" ")}`);
}

/** Moves the real mouse in small steps, so the drawn cursor glides in the recording. */
class Cursor {
  constructor(private readonly page: Page) {}

  async moveTo(target: Locator, xFraction = 0.5) {
    const box = await target.boundingBox();
    if (!box) throw new Error("cursor target is not visible");
    await this.glide(box.x + box.width * xFraction, box.y + box.height / 2);
  }

  async click(target: Locator) {
    await this.moveTo(target);
    await this.page.waitForTimeout(150);
    await this.page.mouse.down();
    await this.page.mouse.up();
  }

  /** Runs along a chart's plot so its tooltip follows the periods. */
  async sweep(chart: Locator) {
    const box = await chart.boundingBox();
    if (!box) throw new Error("chart is not visible");
    const y = box.y + box.height * 0.5;
    await this.glide(box.x + box.width * 0.12, y);
    await this.glide(box.x + box.width * 0.92, y, 70);
    await this.page.waitForTimeout(500);
  }

  private async glide(x: number, y: number, steps = 24) {
    await this.page.mouse.move(x, y, { steps });
  }
}

/** Draws a pointer where the mouse is; headless recordings have none. */
function showCursor() {
  const draw = () => {
    const dot = document.createElement("div");
    dot.setAttribute("aria-hidden", "true");
    dot.style.cssText =
      "position:fixed;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;" +
      "background:rgba(255,255,255,.85);box-shadow:0 0 0 2px rgba(0,0,0,.35),0 2px 8px rgba(0,0,0,.4);" +
      "pointer-events:none;z-index:2147483647;transition:transform .12s ease;transform:translate(-100px,-100px)";
    document.body.appendChild(dot);
    let at = "translate(-100px,-100px)";
    window.addEventListener("mousemove", (event) => {
      at = `translate(${event.clientX}px,${event.clientY}px)`;
      dot.style.transform = at;
    }, true);
    window.addEventListener("mousedown", () => (dot.style.transform = `${at} scale(.7)`), true);
    window.addEventListener("mouseup", () => (dot.style.transform = at), true);
  };
  if (document.body) draw();
  else document.addEventListener("DOMContentLoaded", draw);
}
