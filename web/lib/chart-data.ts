import type { BarChartSpec, LineChartSpec } from "./types";

/**
 * Chart rows built from the server's chart records. Amounts shown as text
 * (tooltips, end labels, bar labels) are the server's strings; numbers here
 * only place marks (ADR 0006).
 */

/**
 * Categorical slots in their validated order (globals.css). A series past the
 * last slot is drawn muted rather than given a generated hue.
 */
export const SERIES_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
] as const;

export interface LineSeries {
  /** Positional data key: company names such as "Apple Inc." read as paths. */
  key: string;
  name: string;
  color: string;
}

export interface LineRow {
  period: string;
  amounts: Record<string, string>;
  /** Series whose latest point is in this row. */
  last?: string[];
  [series: string]: string | number | null | Record<string, string> | string[] | undefined;
}

export function lineSeries(spec: LineChartSpec): LineSeries[] {
  return spec.series.map((name, index) => ({
    key: `s${index}`,
    name,
    color: SERIES_COLORS[index] ?? "var(--chart-muted)",
  }));
}

export function lineRows(spec: LineChartSpec): LineRow[] {
  const series = lineSeries(spec);
  const lastIndex = new Map<string, number>();
  const rows = spec.records.map((record, index) => {
    const row: LineRow = { period: spec.period_labels[index] ?? String(record.Period ?? ""), amounts: {} };
    for (const { key, name } of series) {
      const value = record[name];
      row[key] = typeof value === "number" && Number.isFinite(value) ? value : null;
      const amount = spec.amounts[index]?.[name];
      if (amount) row.amounts[key] = amount;
      if (row[key] !== null) lastIndex.set(key, index);
    }
    return row;
  });
  for (const { key } of series) {
    const index = lastIndex.get(key);
    if (index === undefined) continue;
    (rows[index].last ??= []).push(key);
  }
  return rows;
}

export interface BarRow {
  name: string;
  value: number;
  amount: string;
  /** The amount, or the reason a value is missing. */
  label: string;
  missing: boolean;
  period: string;
}

export function barRows(spec: BarChartSpec): BarRow[] {
  return spec.records.map((record) => ({
    name: record.Company,
    value: record.Missing ? 0 : record.Value,
    amount: record.Amount,
    label: record.Label,
    missing: record.Missing,
    period: record.Period ?? "",
  }));
}

/**
 * The value axis range. Bars grow from zero; a line pads its own range so a
 * trend is visible, without dipping below zero for positive data.
 */
export function valueDomain(
  values: (number | null | undefined)[],
  { zero }: { zero: boolean },
): [number, number] {
  const finite = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (finite.length === 0) return [0, 1];
  const low = Math.min(...finite);
  const high = Math.max(...finite);
  if (zero) {
    const domain: [number, number] = [Math.min(0, low), Math.max(0, high)];
    return domain[0] === domain[1] ? [0, 1] : domain;
  }
  const span = high - low || Math.abs(high) || 1;
  const pad = span * 0.08;
  const padded = low - pad;
  return [low >= 0 && padded < 0 ? 0 : padded, high + pad];
}

/** Clean axis ticks (steps of 1, 2 or 5 × 10ⁿ) covering the domain. */
export function niceTicks([low, high]: [number, number], count = 5): number[] {
  if (!(high > low)) {
    const [floor, ceiling] = [Math.min(0, low), Math.max(0, high)];
    return ceiling > floor ? niceTicks([floor, ceiling], count) : [0, 1];
  }
  const raw = (high - low) / (count - 1);
  const power = 10 ** Math.floor(Math.log10(raw));
  const error = raw / power;
  const step = power * (error >= Math.sqrt(50) ? 10 : error >= Math.sqrt(10) ? 5 : error >= Math.SQRT2 ? 2 : 1);
  const first = Math.floor(low / step);
  const last = Math.ceil(high / step);
  const ticks: number[] = [];
  for (let i = first; i <= last; i += 1) ticks.push(Number((i * step).toPrecision(12)) || 0);
  return ticks;
}
