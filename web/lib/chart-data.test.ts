import { describe, expect, it } from "vitest";
import { barRows, lineSeries, lineRows, niceTicks, valueDomain, SERIES_COLORS } from "./chart-data";
import type { BarChartSpec, LineChartSpec } from "./types";

// "Compare four quarters" then "add Apple", as the API serves it on the recorded runtime.
const TREND: LineChartSpec = {
  kind: "line",
  title: "Trend",
  metric: "revenue",
  metric_label: "Revenue",
  value_kind: "usd",
  caption: "",
  horizontal: false,
  records: [
    { Period: "2024-06-30", "Microsoft Corporation": 64727000000, "Apple Inc.": 85777000000 },
    { Period: "2024-09-30", "Microsoft Corporation": 65585000000 },
    { Period: "2024-12-31", "Microsoft Corporation": 69627000000, "Apple Inc.": 124300000000 },
    { Period: "2026-03-31", "Microsoft Corporation": 82886000000, "Apple Inc.": 111184000000 },
  ],
  period_labels: ["Jun 30, 2024", "Sep 30, 2024", "Dec 31, 2024", "Mar 31, 2026"],
  series: ["Microsoft Corporation", "Apple Inc."],
  amounts: [
    { "Microsoft Corporation": "$64.73 B", "Apple Inc.": "$85.78 B" },
    { "Microsoft Corporation": "$65.59 B" },
    { "Microsoft Corporation": "$69.63 B", "Apple Inc.": "$124.30 B" },
    { "Microsoft Corporation": "$82.89 B", "Apple Inc.": "$111.18 B" },
  ],
};

const RANKED: BarChartSpec = {
  kind: "bar",
  title: "Comparison",
  metric: "research_and_development",
  metric_label: "Research and development",
  value_kind: "usd",
  caption: "Ordered by market cap; bar length is latest-quarter Research and development.",
  horizontal: true,
  records: [
    {
      Company: "#1 AAPL",
      Value: 8042000000,
      Amount: "$8.04 B",
      Label: "$8.04 B",
      Missing: false,
      Period: "Jan 1, 2026 – Mar 31, 2026",
    },
    { Company: "#2 GOOG", Value: 0, Amount: "", Label: "Missing fact", Missing: true },
  ],
};

describe("lineSeries", () => {
  it("keys series by position, since names like 'Apple Inc.' are not safe data keys", () => {
    expect(lineSeries(TREND)).toEqual([
      { key: "s0", name: "Microsoft Corporation", color: SERIES_COLORS[0] },
      { key: "s1", name: "Apple Inc.", color: SERIES_COLORS[1] },
    ]);
  });

  it("assigns colours in a fixed order and never cycles", () => {
    const many = { ...TREND, series: Array.from({ length: 8 }, (_, i) => `Co ${i}`) };
    const colors = lineSeries(many).map((series) => series.color);
    expect(colors.slice(0, SERIES_COLORS.length)).toEqual([...SERIES_COLORS]);
    expect(new Set(colors.slice(SERIES_COLORS.length))).toEqual(new Set(["var(--chart-muted)"]));
  });
});

describe("lineRows", () => {
  it("carries the server's period labels and amounts, and a gap as null", () => {
    const rows = lineRows(TREND);
    expect(rows[0]).toEqual({
      period: "Jun 30, 2024",
      s0: 64727000000,
      s1: 85777000000,
      amounts: { s0: "$64.73 B", s1: "$85.78 B" },
    });
    expect(rows[1]).toMatchObject({ period: "Sep 30, 2024", s1: null, amounts: { s0: "$65.59 B" } });
  });

  it("marks each series' latest point for its end label", () => {
    const rows = lineRows(TREND);
    expect(rows.map((row) => row.last)).toEqual([undefined, undefined, undefined, ["s0", "s1"]]);
  });
});

describe("barRows", () => {
  it("keeps rank order and the server's strings, with a missing value as no bar", () => {
    expect(barRows(RANKED)).toEqual([
      {
        name: "#1 AAPL",
        value: 8042000000,
        amount: "$8.04 B",
        label: "$8.04 B",
        missing: false,
        period: "Jan 1, 2026 – Mar 31, 2026",
      },
      { name: "#2 GOOG", value: 0, amount: "", label: "Missing fact", missing: true, period: "" },
    ]);
  });
});

describe("valueDomain", () => {
  it("starts bars at zero", () => {
    expect(valueDomain([3, 8], { zero: true })).toEqual([0, 8]);
  });

  it("lets negatives extend below zero", () => {
    expect(valueDomain([-2, 5], { zero: true })).toEqual([-2, 5]);
  });

  it("pads a line's range instead of forcing zero", () => {
    const [low, high] = valueDomain([64, 124], { zero: false });
    expect(low).toBeLessThan(64);
    expect(low).toBeGreaterThanOrEqual(0);
    expect(high).toBeGreaterThan(124);
  });

  it("ignores gaps and survives a flat or empty series", () => {
    expect(valueDomain([null, 5, 5], { zero: false })[0]).toBeLessThan(5);
    expect(valueDomain([], { zero: true })).toEqual([0, 1]);
  });
});

describe("niceTicks", () => {
  it("rounds a padded line range out to clean steps", () => {
    expect(niceTicks([57.9e9, 89.7e9])).toEqual([50e9, 60e9, 70e9, 80e9, 90e9]);
  });

  it("keeps zero on a bar axis and steps in 1, 2 or 5", () => {
    expect(niceTicks([0, 13.84e9])).toEqual([0, 5e9, 10e9, 15e9]);
    expect(niceTicks([0, 0.43])).toEqual([0, 0.1, 0.2, 0.3, 0.4, 0.5]);
  });

  it("spans negatives", () => {
    expect(niceTicks([-2e9, 5e9])).toEqual([-2e9, 0, 2e9, 4e9, 6e9]);
  });

  it("survives a flat range", () => {
    expect(niceTicks([0, 0]).length).toBeGreaterThan(1);
  });
});
