import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import { expect, test, type Browser, type BrowserContextOptions, type Locator, type Page } from "@playwright/test";
import { Analyst } from "../e2e/analyst";
import { findFfmpeg, gifArgs, mp4Args } from "./portfolio-media";
import { SOCIAL_SIZE, socialCardHtml } from "./social-card";

/**
 * Re-captures the README's portfolio media from the window (ADR 0006 cutover
 * criteria): compare four quarters, `add Apple`, then inspect the exact 10-Q source.
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
const REPO = "github.com/bpyman/financial-analyst-agent";
const CHIPS = ["SEC 10-Q facts", "Provenance on every number", "Next.js · FastAPI"];

const FILES = {
  landing: "guided-first-run.png",
  compare: "compare-four-quarters.png",
  inspect: "inspect-exact-source.png",
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

  const inspector = await chooseAppleEvidence(page);
  await frame(page, inspector);
  await shoot(page, FILES.inspect);

  await context.close();
}

/**
 * The social preview: the landing headline beside the fact card from "Verify a
 * quarterly fact", both taken from the window, composed by `social-card.ts`.
 */
async function captureSocial(browser: Browser) {
  const context = await browser.newContext({ ...DARK, viewport: STILL, deviceScaleFactor: 2 });
  const page = await context.newPage();
  const analyst = new Analyst(page);

  await analyst.open();
  const headline = page.getByRole("heading", { level: 1 });
  const muted = (await headline.locator("span").textContent())?.trim() ?? "";
  const lead = ((await headline.textContent()) ?? "").replace(muted, "").trim();

  await analyst.tell("Verify a quarterly fact");
  const factCard = analyst.factCards(/, Microsoft Corporation$/);
  await expect(factCard).toBeVisible();
  await settle(page);
  await page.mouse.move(0, 0);
  const card = await factCard.screenshot({ animations: "disabled" });
  await context.close();

  const composer = await browser.newContext({ viewport: SOCIAL_SIZE, deviceScaleFactor: 1 });
  const canvas = await composer.newPage();
  await canvas.setContent(
    socialCardHtml({ lead, muted, chips: CHIPS, repo: REPO, card: dataUri("image/png", card), fonts: geistFonts() }),
  );
  await settle(canvas);
  await canvas.screenshot({ path: path.join(OUT, FILES.social), animations: "disabled" });
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

  // One click: the four-quarter compare, drawn as a trend with its table.
  await cursor.moveTo(analyst.story("Compare four quarters"));
  await page.waitForTimeout(400);
  const before = await analyst.turnsUsed();
  await cursor.click(analyst.story("Compare four quarters"));
  await analyst.waitForTurn(before + 1);
  await page.waitForTimeout(1200);
  await cursor.sweep(analyst.charts().last());
  await scrollBy(page, 360);
  await page.waitForTimeout(1500);

  // A follow-up patches the analysis instead of starting over.
  const composer = page.getByRole("textbox", { name: "Ask a question" });
  await cursor.click(composer);
  await composer.pressSequentially("add Apple", { delay: 110 });
  await page.waitForTimeout(500);
  const asked = await analyst.turnsUsed();
  await page.keyboard.press("Enter");
  await composer.blur();
  await analyst.waitForTurn(asked + 1);
  await page.waitForTimeout(1200);
  await cursor.sweep(analyst.charts().last());
  await page.waitForTimeout(600);

  // Inspect the exact 10-Q source behind one Apple value.
  const inspector = lastTurn(page).getByRole("region", { name: "Evidence inspector" });
  await smoothScrollTo(page, inspector);
  await page.waitForTimeout(700);
  await cursor.moveTo(inspector.getByRole("combobox", { name: "Evidence item" }));
  await page.waitForTimeout(300);
  await chooseAppleEvidence(page);
  await page.waitForTimeout(1600);
  await cursor.moveTo(inspector.getByRole("link", { name: /filing/i }));
  await page.waitForTimeout(2200);

  const video = page.video();
  if (!video) throw new Error("the walkthrough context did not record a video");
  await context.close();
  const recording = await video.path();

  convert(ffmpeg, mp4Args(recording, path.join(OUT, FILES.mp4), { startAt }));
  convert(ffmpeg, gifArgs(recording, path.join(OUT, FILES.gif), { startAt, fps: 8, width: 880 }));
  rmSync(videoDir, { recursive: true, force: true });
}

function lastTurn(page: Page): Locator {
  return page.locator("[data-turn]:not([data-turn=pending])").last();
}

/** Picks the first standalone 10-Q Apple fact in the last answer's evidence inspector. */
async function chooseAppleEvidence(page: Page): Promise<Locator> {
  const inspector = lastTurn(page).getByRole("region", { name: "Evidence inspector" });
  const select = inspector.getByRole("combobox", { name: "Evidence item" });
  const labels = await select.locator("option").allTextContents();
  for (const [index, label] of labels.entries()) {
    if (!label.includes("Apple")) continue;
    await select.selectOption({ index });
    if ((await inspector.textContent())?.includes("Standalone 10-Q")) return inspector;
  }
  throw new Error(`no standalone 10-Q Apple fact among: ${labels.join(" | ")}`);
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
