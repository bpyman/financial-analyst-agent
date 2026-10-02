import { describe, expect, it } from "vitest";
import { csvFileName, tableCsv } from "./csv";
import { pivotTable } from "./pivot";
import { SERIES } from "./test-tables";
import { parseShareLink, shareLink } from "./share-link";

describe("tableCsv", () => {
  it("writes exact amounts in the order on screen", () => {
    const pivot = pivotTable(SERIES);
    if (!pivot) throw new Error("no pivot");
    const csv = tableCsv(pivot, [3, 2, 1, 0]);
    expect(csv.split("\r\n")).toEqual([
      "Quarter ended,MSFT,AAPL",
      "2025-09-30,77673000000,102466000000",
      "2025-12-31,81273000000,143756000000",
      "2026-03-31,82886000000,111184000000",
      "2026-06-30,90007000000,109417000000",
      "",
    ]);
  });

  it("quotes commas and quotes, and keeps text from reading as a formula", () => {
    const csv = tableCsv(
      {
        headers: ["Company", "Note"],
        keys: ["company_name", "reason"],
        rows: [['Acme, "Inc."', "=HYPERLINK(1)"]],
        numbers: [[null, null]],
      },
      null,
    );
    expect(csv).toBe('Company,Note\r\n"Acme, ""Inc.""",\'=HYPERLINK(1)\r\n');
  });

  it("falls back to the shown text when the server sent no raw cells, and keeps negatives", () => {
    const csv = tableCsv(
      { headers: ["Change"], keys: ["value"], rows: [["-$1.20 B"]], numbers: [[-1.2e9]], raw: [["-1200000000"]] },
      null,
    );
    expect(csv).toBe("Change\r\n-1200000000\r\n");
  });

  it("names the file after the question", () => {
    expect(csvFileName("What was Apple's revenue?")).toBe("what-was-apple-s-revenue.csv");
  });
});

describe("share links", () => {
  it("round-trips a question and a runtime", () => {
    const link = shareLink("https://onfile.example", "Compare Apple & Microsoft revenue?", "recorded");
    expect(link).toBe("https://onfile.example/?q=Compare+Apple+%26+Microsoft+revenue%3F&rt=recorded");
    expect(parseShareLink(new URL(link).search, 2000)).toEqual({
      question: "Compare Apple & Microsoft revenue?",
      runtime: "recorded",
    });
  });

  it("ignores an unknown runtime and refuses an empty or overlong question", () => {
    expect(parseShareLink("?q=Hi&rt=staging", 2000)).toEqual({ question: "Hi", runtime: null });
    expect(parseShareLink("?q=%20%20", 2000)).toBeNull();
    expect(parseShareLink("?rt=live", 2000)).toBeNull();
    expect(parseShareLink(`?q=${"a".repeat(30)}`, 20)).toBeNull();
  });
});
