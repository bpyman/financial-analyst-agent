import { expect, test } from "@playwright/test";
import { Analyst } from "./analyst";

// Each test gets a fresh browser context, so a fresh thread (ADR 0006 cutover criteria).

// The hosted demo is a public demo without live SEC, so it serves only the recorded
// runtime; the local run starts the API with PUBLIC_DEMO off.
const deployed = Boolean(process.env.PLAYWRIGHT_BASE_URL);

test.describe("guided stories", () => {
  test("Verify a quarterly fact shows the fact card and its evidence", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("Verify a quarterly fact");

    const card = analyst.factCards(/, Microsoft Corporation$/);
    await expect(card).toBeVisible();
    await expect(card).toContainText("$");
    await expect(card).toContainText("10-Q");
    await expect(card.getByRole("link", { name: /filing/i })).toBeVisible();
    await expect(page.getByRole("region", { name: "Evidence inspector" })).toBeVisible();
  });

  test("Compare four quarters draws a trend and its table", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("Compare four quarters");

    await expect(analyst.charts()).toHaveCount(1);
    await expect(analyst.charts()).toContainText("Revenue");
    await expect(analyst.tables()).toBeVisible();
    await expect(analyst.tables().getByRole("row")).toHaveCount(5);
  });

  test("Rank then inspect filings ranks ten companies and links each filing", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("Rank then inspect filings");

    await expect(analyst.charts()).toHaveCount(1);
    const table = analyst.tables();
    await expect(table.getByRole("row")).toHaveCount(11);
    await expect(table.getByRole("link", { name: /filing/i })).toHaveCount(10);

    await table.getByRole("radio", { name: "Full" }).click();
    await expect(table.getByRole("columnheader", { name: /accession/i })).toBeVisible();
  });

  test("What changed in the 10-Q shows each changed section", async ({ page }) => {
    const analyst = new Analyst(page);
    await analyst.open();
    await analyst.tell("What changed in the 10-Q");

    const changes = page.getByRole("region", { name: "Filing changes" });
    const kind = "(added|removed|changed)$";
    await expect(changes.getByRole("article")).toHaveCount(2);
    for (const section of ["Management's Discussion and Analysis", "Risk Factors"]) {
      const name = new RegExp(`^${section}, ${kind}`);
      await expect(changes.getByRole("article", { name })).toBeVisible();
    }
    await expect(changes.getByRole("link", { name: "Open previous filing" }).first()).toBeVisible();
  });
});

test("compare four quarters, then add Apple", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Compare four quarters");
  await analyst.ask("add Apple");

  await expect(analyst.charts()).toHaveCount(2);
  const legend = analyst.charts().last().getByRole("list", { name: "Series" });
  await expect(legend.getByRole("listitem")).toHaveText([/Microsoft Corporation/, /Apple Inc\./]);
  await expect(analyst.activeAnalysis()).toContainText("AAPL");
  await expect(analyst.counter()).toHaveText(/^2 of /);
});

test("a clarify button answers the question and closes it", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.ask("What was Google's latest quarterly profit?");

  const clarify = analyst.clarify();
  await expect(clarify).toBeVisible();
  const candidates = clarify.getByRole("button");
  await expect(candidates).toHaveText([/Gross profit/, /Operating income/, /Net income/]);
  await expect(candidates.first()).toBeEnabled();

  await analyst.choose(/Net income/);

  await expect(analyst.factCards(/^Net income, /)).toBeVisible();
  await expect(clarify.getByRole("button", { name: /Net income/ })).toBeDisabled();
  await expect(clarify).toContainText("Answered below.");
  // The answer bubble shows the chosen label, not the slug it sent.
  await expect(page.getByTitle("Sent as net_income")).toHaveText("Net income");
});

test("a reload resumes the thread and Start over clears it", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");

  await page.reload();
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  await expect(analyst.counter()).toHaveText(/^1 of /);

  await analyst.startOver();
  await expect(analyst.counter()).toHaveText(/^0 of /);

  await page.reload();
  await expect(analyst.story("Verify a quarterly fact")).toBeEnabled();
  await expect(analyst.conversation()).toBeHidden();
});

test("the storefront reports the deployment's runtime and asks for that runtime's snapshot", async ({ page }) => {
  const asked = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/meta");
  await new Analyst(page).open();
  const response = await asked;

  expect(new URL(response.url()).searchParams.get("runtime")).toBe("recorded");
  expect((await response.json()).runtime).toEqual({ default: "recorded", locked: deployed });
});

test("the composer takes its message limit from the server", async ({ page }) => {
  await page.route("**/api/meta**", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), max_message_chars: 50 } });
  });
  await new Analyst(page).open();

  await expect(page.getByRole("textbox", { name: "Ask a question" })).toHaveAttribute("maxlength", "50");
});

test("a question sent before the storefront loads leaves the runtime to the deployment", async ({ page }) => {
  let releaseMeta = () => {};
  const metaHeld = new Promise<void>((resolve) => (releaseMeta = resolve));
  await page.route("**/api/meta**", async (route) => {
    await metaHeld;
    await route.continue();
  });
  const analyst = new Analyst(page);
  await page.goto("/");

  const created = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/api/threads",
  );
  await page.getByRole("textbox", { name: "Ask a question" }).fill("What was Microsoft's latest quarterly pretax income?");
  await page.keyboard.press("Enter");
  expect((await created).postDataJSON()).toEqual({});

  releaseMeta();
  await analyst.waitForTurn(1);
});

test("a reload while a turn runs picks the answer up when it lands", async ({ page }) => {
  const analyst = new Analyst(page);
  await analyst.open();
  await analyst.tell("Verify a quarterly fact");

  // The server reports the turn still in flight for the first two reads after the reload.
  let inFlightReads = 2;
  await page.route(/\/api\/threads\/[0-9a-f-]+$/, async (route) => {
    if (route.request().method() !== "GET" || inFlightReads === 0) return route.continue();
    inFlightReads -= 1;
    const response = await route.fetch();
    const view = await response.json();
    await route.fulfill({ response, json: { ...view, turns: [], turn_in_flight: true } });
  });
  await page.reload();

  await expect(page.getByText("Finishing your last question…")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analysis running" })).toBeDisabled();
  await expect(analyst.factCards(/, Microsoft Corporation$/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
  await expect(analyst.counter()).toHaveText(/^1 of /);
});
