import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SafeMarkdown } from "./markdown";

const render = (text: string, citations: { index: number; title: string; url: string }[] = []) =>
  renderToStaticMarkup(createElement(SafeMarkdown, { text, citations }));

describe("SafeMarkdown", () => {
  it("renders prose, lists, and emphasis", () => {
    const html = render("Demand **rose**.\n\n- Cloud\n- AI");
    expect(html).toContain("<strong>rose</strong>");
    expect(html).toContain("<li>Cloud</li>");
  });

  it("never renders raw HTML", () => {
    const html = render('Hi <script>alert(1)</script> <img src=x onerror="alert(1)"> <a href="https://x.test">x</a>');
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("onerror=\"");
    expect(html).not.toMatch(/<a /);
  });

  it("drops links that are not http(s), keeping their text", () => {
    const html = render("[click](javascript:alert(1)) and [data](data:text/html,hi) and [rel](/api/x)");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("data:text");
    expect(html).not.toMatch(/<a /);
    expect(html).toContain("click");
  });

  it("opens safe links in a new tab without an opener", () => {
    const html = render("[SEC](https://www.sec.gov/x)");
    expect(html).toContain('href="https://www.sec.gov/x"');
    expect(html).toContain('rel="noreferrer noopener"');
    expect(html).toContain('target="_blank"');
  });

  it("draws no images, only their alt text", () => {
    const html = render("![tracking pixel](https://evil.test/p.png)");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("evil.test");
  });

  it("links [n] markers to their source", () => {
    const html = render("Loadings slowed [1].", [
      { index: 1, title: "Hormuz closures slow crude loadings", url: "https://example.test/hormuz" },
    ]);
    expect(html).toContain('href="https://example.test/hormuz"');
    expect(html).toContain('aria-label="Source 1: Hormuz closures slow crude loadings"');
  });

  it("leaves a marker whose source URL is unsafe as plain text", () => {
    const html = render("Claim [1].", [{ index: 1, title: "Bad", url: "javascript:alert(1)" }]);
    expect(html).not.toContain("javascript:");
    expect(html).toContain("[1]");
  });
});
