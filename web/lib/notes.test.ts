import { describe, expect, it } from "vitest";
import { answerFilings, splitNotes } from "./notes";
import type { Presentation } from "./types";

describe("splitNotes", () => {
  it("puts the † note under the figures, the snapshot in the caption, and the rest on one line", () => {
    const split = splitNotes([
      "Universe snapshot as of Sep 27, 2026, 10:43 PM UTC",
      "† Derived from reported figures because the filings do not report it on its own.",
      "Filings report quarters, not months or weeks, so this shows the latest quarter.",
    ]);
    expect(split.snapshot).toBe("Universe snapshot as of Sep 27, 2026, 10:43 PM UTC");
    expect(split.footnotes).toEqual(["† Derived from reported figures because the filings do not report it on its own."]);
    expect(split.notes).toEqual(["Filings report quarters, not months or weeks, so this shows the latest quarter."]);
  });
});

describe("answerFilings", () => {
  it("lists each filing once, whatever passage a link points into", () => {
    const item = {
      label: "",
      amount: "",
      raw_amount: "",
      company_name: "Microsoft Corporation",
      ticker: "MSFT",
      cik: "",
      concept: "",
      period_label: "",
      accession_number: "0001193125-26-323660",
      form: "10-K",
      source_url: "https://www.sec.gov/a.htm#:~:text=Revenue",
      selection_rule: "",
    };
    const filings = answerFilings({
      fact_card: null,
      evidence: [item, { ...item, source_url: "https://www.sec.gov/a.htm" }, { ...item, source_url: "javascript:alert(1)" }],
      disclosures: [],
    } as unknown as Presentation);
    expect(filings).toEqual([
      { url: "https://www.sec.gov/a.htm", label: "Microsoft Corporation, 10-K 0001193125-26-323660" },
    ]);
  });
});
