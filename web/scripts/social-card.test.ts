import { describe, expect, it } from "vitest";
import { SOCIAL_SIZE, socialCardHtml, type SocialCard } from "./social-card";

const card: SocialCard = {
  lead: "Ask about a company.",
  muted: "Get the number and the filing behind it.",
  chips: ["SEC 10-Q facts", "Provenance on every number"],
  repo: "github.com/bpyman/onfile",
  card: "data:image/png;base64,AAAA",
  fonts: { sans: "data:font/woff2;base64,SANS", mono: "data:font/woff2;base64,MONO" },
};

describe("socialCardHtml", () => {
  it("renders at LinkedIn's 1.91:1 link preview size", () => {
    expect(SOCIAL_SIZE).toEqual({ width: 1200, height: 628 });
    const html = socialCardHtml(card);
    expect(html).toContain("width:1200px;height:628px");
  });

  it("gives the chart about 60% of the width", () => {
    const width = Number(/\.card\{[^}]*width:(\d+)px/.exec(socialCardHtml(card))?.[1]);
    expect(width / SOCIAL_SIZE.width).toBeGreaterThanOrEqual(0.55);
    expect(width / SOCIAL_SIZE.width).toBeLessThanOrEqual(0.65);
  });

  it("sets the landing headline with its muted second sentence", () => {
    const html = socialCardHtml(card);
    expect(html).toContain("<h1>Ask about a company.<br><span>Get the number and the filing behind it.</span></h1>");
  });

  it("shows the captured chart, the chips, and the repo", () => {
    const html = socialCardHtml(card);
    expect(html).toContain('src="data:image/png;base64,AAAA"');
    expect(html).toContain("SEC 10-Q facts</span>");
    expect(html).toContain("Provenance on every number</span>");
    expect(html).toContain("github.com/bpyman/onfile");
  });

  it("names the project beside its mark", () => {
    const html = socialCardHtml(card);
    expect(html).toMatch(/<div class="brand"><div class="logo">.*<\/div>Onfile<\/div>/);
  });

  it("embeds its fonts so the page needs no network", () => {
    const html = socialCardHtml(card);
    expect(html).toContain('url(data:font/woff2;base64,SANS) format("woff2")');
    expect(html).toContain('url(data:font/woff2;base64,MONO) format("woff2")');
    expect(html).not.toMatch(/https?:\/\//);
  });

  it("escapes text it did not write", () => {
    const html = socialCardHtml({ ...card, lead: "R&D <spend>" });
    expect(html).toContain("R&amp;D &lt;spend&gt;");
  });
});
