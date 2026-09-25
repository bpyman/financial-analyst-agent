import { describe, expect, it } from "vitest";
import { tableColumns, hasProvenance } from "./table-view";
import type { DisplayTable } from "./types";

// Shapes captured from /api/threads/{id}/turns on the recorded runtime.
const TREND: DisplayTable = {
  headers: [
    "Company",
    "Ticker",
    "CIK",
    "Revenue",
    "Currency",
    "Start date",
    "End date",
    "Form",
    "Accession number",
    "Taxonomy",
    "Concept",
    "Source URL",
  ],
  keys: [
    "company_name",
    "ticker",
    "cik",
    "value",
    "currency",
    "start_date",
    "end_date",
    "form",
    "accession_number",
    "taxonomy",
    "concept",
    "source_url",
  ],
  rows: [
    [
      "Microsoft Corporation",
      "MSFT",
      "0000789019",
      "$82.89 B",
      "USD",
      "Jan 1, 2026",
      "Mar 31, 2026",
      "10-Q",
      "0001193125-26-191507",
      "us-gaap",
      "RevenueFromContractWithCustomerExcludingAssessedTax",
      "https://www.sec.gov/Archives/edgar/data/789019/000119312526191507/msft-20260331.htm",
    ],
  ],
  numbers: [[null, null, null, 82886000000, null, null, null, null, null, null, null, null]],
};

const RANK: DisplayTable = {
  headers: [
    "Rank",
    "Company",
    "Ticker",
    "Research and development",
    "Start date",
    "End date",
    "Form",
    "Accession number",
    "Concept",
    "Source URL",
    "Reason",
  ],
  keys: [
    "rank",
    "company_name",
    "ticker",
    "value",
    "start_date",
    "end_date",
    "form",
    "accession_number",
    "concept",
    "source_url",
    "reason",
  ],
  rows: [],
  numbers: [],
};

const keysOf = (table: DisplayTable, mode: "compact" | "full") =>
  tableColumns(table, mode).map((column) => column.key);

describe("tableColumns", () => {
  it("keeps the compact view to what a reader compares", () => {
    expect(keysOf(TREND, "compact")).toEqual(["company_name", "value", "end_date", "source_url"]);
    expect(keysOf(RANK, "compact")).toEqual([
      "rank",
      "company_name",
      "value",
      "end_date",
      "reason",
      "source_url",
    ]);
  });

  it("reveals the provenance columns in the full view, filing link last", () => {
    expect(keysOf(TREND, "full")).toEqual([
      "company_name",
      "cik",
      "value",
      "currency",
      "start_date",
      "end_date",
      "form",
      "accession_number",
      "taxonomy",
      "concept",
      "source_url",
    ]);
  });

  it("uses the server's headers and points at the server's cells", () => {
    const [company, value] = tableColumns(TREND, "compact");
    expect(company).toMatchObject({ header: "Company", index: 0, tickerIndex: 1, kind: "company" });
    expect(value).toMatchObject({ header: "Revenue", index: 3, kind: "value", numeric: true });
    expect(TREND.rows[0][value.index]).toBe("$82.89 B");
  });

  it("marks identifiers for copying and the source URL as a filing link", () => {
    const full = tableColumns(TREND, "full");
    const byKey = Object.fromEntries(full.map((column) => [column.key, column]));
    expect(byKey.cik.kind).toBe("identifier");
    expect(byKey.accession_number.kind).toBe("identifier");
    expect(byKey.source_url.kind).toBe("filing");
    expect(byKey.concept.kind).toBe("code");
    expect(byKey.end_date.numeric).toBe(false);
  });

  it("right-aligns rank and value only", () => {
    const numeric = tableColumns(RANK, "full")
      .filter((column) => column.numeric)
      .map((column) => column.key);
    expect(numeric).toEqual(["rank", "value"]);
  });

  it("keeps a lone ticker column when there is no company name", () => {
    const table: DisplayTable = {
      headers: ["Ticker", "Revenue"],
      keys: ["ticker", "value"],
      rows: [["MSFT", "$1.00 B"]],
      numbers: [[null, 1e9]],
    };
    expect(keysOf(table, "compact")).toEqual(["ticker", "value"]);
  });

  it("keeps unknown server columns visible", () => {
    const table: DisplayTable = {
      headers: ["Company", "Metric", "Value"],
      keys: ["company_name", "metric", "value"],
      rows: [],
      numbers: [],
    };
    expect(keysOf(table, "compact")).toEqual(["company_name", "metric", "value"]);
  });
});

describe("hasProvenance", () => {
  it("offers the full view only when it adds columns", () => {
    expect(hasProvenance(TREND)).toBe(true);
    expect(
      hasProvenance({ headers: ["Company", "Revenue"], keys: ["company_name", "value"], rows: [], numbers: [] }),
    ).toBe(false);
  });
});
