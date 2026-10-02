import { describe, expect, it } from "vitest";
import { pivotTable } from "./pivot";
import { sortedRowIndices } from "./table-sort";
import { SERIES } from "./test-tables";

describe("pivotTable", () => {
  it("puts quarters in rows and companies in columns, keeping marks and evidence", () => {
    const pivot = pivotTable(SERIES);
    expect(pivot).not.toBeNull();
    if (!pivot) return;
    expect(pivot.headers).toEqual(["Quarter ended", "MSFT", "AAPL"]);
    expect(pivot.rows.map((row) => row[0])).toEqual(["Jun 30, 2026", "Mar 31, 2026", "Dec 31, 2025", "Sep 30, 2025"]);
    expect(pivot.rows[0]).toEqual(["Jun 30, 2026", "$90.01 B †", "$109.42 B"]);
    expect(pivot.rows[3]).toEqual(["Sep 30, 2025", "$77.67 B", "$102.47 B †"]);
    expect(pivot.evidence?.[0]).toEqual([null, 0, 6]);
    expect(pivot.raw?.[0]).toEqual(["2026-06-30", "90007000000", "109417000000"]);
    // Apple's own quarter end stays with its cell.
    expect(pivot.titles?.[0]).toEqual([null, "Microsoft Corporation, quarter ended Jun 30, 2026", "Apple Inc., quarter ended Jun 27, 2026"]);
  });

  it("sorts by quarter or by one company's column", () => {
    const pivot = pivotTable(SERIES);
    if (!pivot) throw new Error("no pivot");
    expect(sortedRowIndices(pivot, { key: pivot.keys[0], direction: "ascending" })).toEqual([3, 2, 1, 0]);
    expect(sortedRowIndices(pivot, { key: pivot.keys[2], direction: "descending" })).toEqual([2, 1, 0, 3]);
  });

  it("leaves a table alone when it is not several companies over several quarters", () => {
    const one = { ...SERIES, rows: SERIES.rows.slice(0, 4), numbers: SERIES.numbers.slice(0, 4) };
    expect(pivotTable(one)).toBeNull();
    const latest = { ...SERIES, rows: [SERIES.rows[0], SERIES.rows[4]], numbers: [SERIES.numbers[0], SERIES.numbers[4]] };
    expect(pivotTable(latest)).toBeNull();
    const twoMetrics = { ...SERIES, keys: ["company_name", "ticker", "value:revenue", "value:net_income", "end_date"] };
    expect(pivotTable(twoMetrics)).toBeNull();
  });

  it("gives a company missing a quarter an empty cell", () => {
    const gap = {
      ...SERIES,
      rows: SERIES.rows.slice(0, 7),
      numbers: SERIES.numbers.slice(0, 7),
      evidence: SERIES.evidence?.slice(0, 7),
      raw: SERIES.raw?.slice(0, 7),
    };
    const pivot = pivotTable(gap);
    expect(pivot?.rows[3]).toEqual(["Sep 30, 2025", "$77.67 B", ""]);
    expect(pivot?.numbers[3][2]).toBeNull();
  });
});
