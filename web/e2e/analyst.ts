import { expect, type Locator, type Page } from "@playwright/test";

/** What an analyst does in the window, in the words the screen uses. */
export class Analyst {
  constructor(readonly page: Page) {}

  /** Opens the window on an empty thread with the guided stories loaded. */
  async open() {
    await this.page.goto("/");
    await expect(this.story("Verify a quarterly fact")).toBeEnabled();
  }

  story(label: string): Locator {
    return this.page.getByRole("region", { name: "Guided stories" }).getByRole("button", { name: label });
  }

  /** Clicks a guided story and waits for its answer. */
  async tell(label: string) {
    const before = await this.turnsUsed();
    await this.story(label).click();
    await this.waitForTurn(before + 1);
  }

  /** Types a message into the composer, sends it, and waits for the answer. */
  async ask(message: string) {
    const before = await this.turnsUsed();
    await this.page.getByRole("textbox", { name: "Ask a question" }).fill(message);
    await this.page.keyboard.press("Enter");
    await this.waitForTurn(before + 1);
  }

  /** Clicks a clarify candidate and waits for the answer it sends. */
  async choose(candidate: RegExp) {
    const before = await this.turnsUsed();
    await this.clarify().first().getByRole("button", { name: candidate }).click();
    await this.waitForTurn(before + 1);
  }

  async startOver() {
    await this.page.getByRole("button", { name: "Start over" }).click();
    await expect(this.conversation()).toBeHidden();
    await expect(this.story("Verify a quarterly fact")).toBeEnabled();
  }

  counter(): Locator {
    return this.page.getByLabel("Turns used");
  }

  /** Turns used on this thread, from the status line (0 before the first turn). */
  async turnsUsed(): Promise<number> {
    if ((await this.counter().count()) === 0) return 0;
    const text = (await this.counter().textContent()) ?? "";
    return Number(text.split(" ")[0]) || 0;
  }

  async waitForTurn(count: number) {
    await expect(this.counter()).toHaveText(new RegExp(`^${count} of \\d+ turns?$`));
    await expect(this.page.getByRole("button", { name: "Send" })).toBeVisible();
  }

  conversation(): Locator {
    return this.page.getByRole("list", { name: "Conversation" });
  }

  factCards(company: string | RegExp): Locator {
    return this.page.getByRole("region", { name: company });
  }

  charts(): Locator {
    return this.page.getByRole("figure");
  }

  tables(): Locator {
    return this.page.getByRole("region", { name: "Answer table" });
  }

  clarify(): Locator {
    return this.page.getByRole("region", { name: "Clarify" });
  }

  activeAnalysis(): Locator {
    return this.page.getByRole("list", { name: "Active analysis" });
  }
}
