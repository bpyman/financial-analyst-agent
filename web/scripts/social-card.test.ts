import { describe, expect, it } from "vitest";
import { SOCIAL_SIZE, socialCardHtml, type SocialCard } from "./social-card";

const card: SocialCard = {
  lead: "Ask about a company.",
  muted: "Get the number and the filing behind it.",
  chips: ["SEC 10-Q facts", "Provenance on every number"],
  repo: "github.com/bpyman/financial-analyst-agent",
  card: "data:image/png;base64,AAAA",
  fonts: { sans: "data:font/woff2;base64,SANS", mono: "data:font/woff2;base64,MONO" },
};

describe("socialCardHtml", () => {
  it("renders at GitHub's 1280×640 social preview size", () => {
    expect(SOCIAL_SIZE).toEqual({ width: 1280, height: 640 });
    const html = socialCardHtml(card);
    expect(html).toContain("width:1280px;height:640px");
  });

  it("sets the landing headline with its muted second sentence", () => {
    const html = socialCardHtml(card);
    expect(html).toContain("<h1>Ask about a company.<br><span>Get the number and the filing behind it.</span></h1>");
  });

  it("shows the captured fact card, the chips, and the repo", () => {
    const html = socialCardHtml(card);
    expect(html).toContain('src="data:image/png;base64,AAAA"');
    expect(html).toContain("SEC 10-Q facts</span>");
    expect(html).toContain("Provenance on every number</span>");
    expect(html).toContain("github.com/bpyman/financial-analyst-agent");
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
