import { expect, test, type Page } from "@playwright/test";
import { Analyst } from "./analyst";

// Faults the hosted window meets (a sleeping or refusing API, odd replies, a
// full conversation) and the keyboard paths through it. Faults are injected
// with page.route; everything else is the recorded API.

const THREAD = /\/api\/threads\/[0-9a-f-]+$/;
const TURNS = /\/api\/threads\/[0-9a-f-]+\/turns$/;
const storedId = (page: Page) => page.evaluate(() => localStorage.getItem("financial-analyst-agent.thread-id"));

/** Serves every GET of the thread through `change`, as a reload would read it. */
async function rewriteThread(page: Page, change: (view: Record<string, unknown>) => void) {
  await page.route(THREAD, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const view = await response.json();
    change(view);
    await route.fulfill({ response, json: view });
  });
}

test("a saved answer missing fields still shows, with the rest of the thread", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");

  await rewriteThread(page, (view) => {
    const [turn] = view.turns as { presentation: Record<string, unknown> }[];
    turn.presentation.banners = null;
    turn.presentation.evidence = [{ amount: null }];
    (turn.presentation.fact_card as Record<string, unknown>).period_label = null;
  });
  await page.reload();

  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  await expect(page.getByText("This page couldn't be shown")).toBeHidden();
  await expect(analyst.counter()).toHaveAttribute("data-turns", "1");
});

test("a reply the window cannot read says so, rather than that the service is down", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await page.route(TURNS, (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: "event: progress\ndata: {not json\n\n" }),
  );
  await analyst.story("Verify a quarterly fact").click();

  const failed = page.locator('[data-turn="pending"]');
  await expect(failed).toContainText("couldn't read");
  await expect(failed).not.toContainText("unreachable");
});

test("Start over keeps the conversation when a new one cannot start, and says how long to wait", async ({
  page,
}) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  const savedId = await storedId(page);
  const deleted: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "DELETE") deleted.push(request.url());
  });
  await page.route("**/api/threads", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 429, headers: { "retry-after": "600" }, json: { detail: "Slow down." } })
      : route.continue(),
  );

  await page.getByRole("button", { name: "Start over" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Clear conversation" }).click();

  await expect(page.getByText(/started a lot of new conversations.*in about 10 minutes/)).toBeVisible();
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  expect(await storedId(page)).toBe(savedId);
  expect(deleted).toEqual([]);
});

test("a full conversation stops taking questions and offers Start over", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.ask("How is Nvidia doing?");

  let used = 20;
  await rewriteThread(page, (view) => {
    view.turn_count = used;
  });
  await page.reload();
  await expect(page.getByText("5 questions left in this conversation")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Suggested next questions" })).toBeVisible();

  used = 25;
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Ask a question" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Conversation full" })).toBeDisabled();
  await expect(page.getByRole("navigation", { name: "Suggested next questions" })).toBeHidden();
});

test("a failed turn on a full conversation offers Start over, never Try again", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  // The thread had one question left; the server refuses this one, then reports the count.
  let used = 24;
  await rewriteThread(page, (view) => {
    view.turn_count = used;
  });
  await page.reload();
  await page.route(TURNS, async (route) => {
    used = 25;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'event: error\ndata: {"message": "This thread has reached its turn limit. Start over to continue."}\n\n',
    });
  });
  await page.getByRole("textbox", { name: "Ask a question" }).fill("add Apple");
  // After a reload the window first checks for a turn still running; Send waits for it.
  await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
  await page.keyboard.press("Enter");

  const failed = page.locator('[data-turn="pending"]');
  await expect(failed.getByRole("button", { name: "Start over" })).toBeVisible();
  await expect(failed.getByRole("button", { name: "Try again" })).toBeHidden();
});

test("the confirm panel starts on Cancel, keeps focus, and hands it back", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  // A notice the panel's Escape must leave alone.
  await page.route("**/api/threads", (route) =>
    route.request().method() === "POST" ? route.fulfill({ status: 503, json: { detail: "Busy." } }) : route.continue(),
  );
  const startOver = page.getByRole("button", { name: "Start over" });
  await startOver.click();
  await page.getByRole("button", { name: "Clear conversation" }).click();
  await expect(page.getByText("Busy.")).toBeVisible();

  await startOver.focus();
  await page.keyboard.press("Enter");
  const panel = page.getByRole("alertdialog", { name: "Start over?" });
  await expect(panel).toHaveAttribute("aria-modal", "true");
  await expect(panel.getByRole("button", { name: "Cancel" })).toBeFocused();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(panel.getByRole("button", { name: "Cancel" })).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(startOver).toBeFocused();
  await expect(page.getByText("Busy.")).toBeVisible();
});

test("on a resumed thread the first Tab reaches the skip link, which goes to the question box", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  await page.reload();
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Your conversation");
  await expect(page.getByRole("heading", { level: 2, name: "Answer 1" })).toBeAttached();

  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to the question box" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("textbox", { name: "Ask a question" })).toBeFocused();
});

test("a landed answer is announced", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  await expect(page.getByRole("status").filter({ hasText: "Answer ready." })).toBeAttached();
});

test("the landing page offers its stories while the service is down", async ({ page }) => {
  await page.route("**/api/meta**", (route) => route.abort("connectionrefused"));
  const analyst = new Analyst(page);
  await page.goto("/");

  await expect(analyst.story("Rank then inspect filings")).toBeVisible();
  await expect(page.getByRole("region", { name: "What you can ask" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("a saved conversation that cannot load offers a new one without deleting it", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");
  const savedId = await storedId(page);
  await page.route(THREAD, (route) =>
    route.request().method() === "GET" && route.request().url().endsWith(savedId ?? "")
      ? route.fulfill({ status: 503, json: { detail: "Unavailable." } })
      : route.continue(),
  );
  const deleted: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "DELETE") deleted.push(request.url());
  });
  await page.reload();

  await expect(page.getByText("Your conversation couldn't be loaded.")).toBeVisible();
  await page.getByRole("button", { name: "Start a new conversation" }).click();
  await expect(analyst.story("Verify a quarterly fact")).toBeEnabled();
  expect(await storedId(page)).not.toBe(savedId);
  expect(deleted).toEqual([]);
});

test("Copy with sources says when the clipboard refuses", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: () => Promise.reject(new Error("blocked")) },
    });
  });
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");

  await page.getByRole("button", { name: /Copy with sources/ }).click();
  await expect(page.getByRole("button", { name: /Couldn't copy/ })).toBeVisible();
});

test("a cold start says it is waking, and for how long", async ({ page }) => {
  // The service sleeps: nothing that would show it awake answers.
  await page.route("**/api/health", () => undefined);
  await page.route("**/api/meta**", () => undefined);
  await page.route(TURNS, () => undefined);
  const analyst = new Analyst(page);
  await page.goto("/");
  await expect(page.getByText("Waking the analysis service…")).toBeVisible();

  await analyst.story("Verify a quarterly fact").click();
  const pending = page.locator('[data-turn="pending"]');
  await expect(pending).toContainText("Waking the analysis service…");
  await expect(pending).toContainText(/\d+ s/);
});

test("a slow live answer offers Recorded, and asks there", async ({ page }) => {
  test.setTimeout(90_000);
  await page.route(TURNS, () => undefined);
  const analyst = new Analyst(page);
  await analyst.open();
  await page.getByRole("radio", { name: "Live" }).click();
  await expect(page.getByRole("radio", { name: "Live" })).toBeChecked();

  await page.getByRole("textbox", { name: "Ask a question" }).fill("What was Microsoft's latest quarterly pretax income?");
  await page.keyboard.press("Enter");
  const pending = page.locator('[data-turn="pending"]');
  // The service answered already, so this is work, not a wake-up.
  await expect(pending).toContainText("Sending your question…");
  const tryRecorded = pending.getByRole("button", { name: "Try Recorded instead" });
  await expect(tryRecorded).toBeVisible({ timeout: 30_000 });
  await page.unroute(TURNS);
  await tryRecorded.click();

  await expect(page.getByRole("radio", { name: "Recorded" })).toBeChecked();
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  await expect(analyst.counter()).toHaveAttribute("data-turns", "1");
});

test.describe("the proxy", () => {
  test("answers HEAD on health, refuses an encoded slash, and lets nothing cache a thread", async ({
    page,
    request,
  }) => {
    expect((await request.head("/api/health")).status()).toBe(200);
    expect((await request.get("/api/threads/a%2Fb")).status()).toBe(404);

    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("Verify a quarterly fact");
    const thread = await request.get(`/api/threads/${await storedId(page)}`);
    expect(thread.headers()["cache-control"]).toBe("private, no-store");
  });
});
