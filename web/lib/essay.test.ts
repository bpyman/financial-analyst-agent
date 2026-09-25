import { describe, expect, it } from "vitest";
import { citationIndex, linkCitations, sourceHost } from "./essay";

describe("linkCitations", () => {
  it("turns [n] markers into source links", () => {
    expect(linkCitations("Loadings slowed [1]. Prices rose [2].", 2)).toBe(
      "Loadings slowed [1](#source-1). Prices rose [2](#source-2).",
    );
  });

  it("links adjacent markers separately", () => {
    expect(linkCitations("Both agree [1][2].", 2)).toBe("Both agree [1](#source-1)[2](#source-2).");
  });

  it("leaves markers with no matching source as text", () => {
    expect(linkCitations("See [3] and [0].", 2)).toBe("See [3] and [0].");
  });

  it("leaves markdown links and definitions alone", () => {
    expect(linkCitations("A [1](https://example.com) link.", 1)).toBe("A [1](https://example.com) link.");
    expect(linkCitations("[1]: https://example.com", 1)).toBe("[1]: https://example.com");
  });

  it("does nothing without sources", () => {
    expect(linkCitations("A claim [1].", 0)).toBe("A claim [1].");
  });
});

describe("citationIndex", () => {
  it("reads the source number back from a marker link", () => {
    expect(citationIndex("#source-2")).toBe(2);
    expect(citationIndex("#source-x")).toBeNull();
    expect(citationIndex("https://example.com")).toBeNull();
  });
});

describe("sourceHost", () => {
  it("names the site without www", () => {
    expect(sourceHost("https://www.reuters.com/markets/x")).toBe("reuters.com");
    expect(sourceHost("https://example.test/hormuz-exxon")).toBe("example.test");
  });

  it("is empty for an unsafe or broken URL", () => {
    expect(sourceHost("javascript:alert(1)")).toBe("");
    expect(sourceHost("not a url")).toBe("");
  });
});
