import type { DisplayTable } from "./types";

/**
 * Several companies over several quarters, turned to read across: a row per
 * quarter, a column per company headed by its ticker. Cells keep the server's
 * strings (ADR 0006), † marks included; the move only rearranges them.
 */
export interface ShownTable extends DisplayTable {
  /** A cell's own company and quarter end, when its row stands for several dates. */
  titles?: (string | null)[][];
}

// Apple's quarter ending June 27 and Microsoft's ending June 30 are one quarter.
const SAME_QUARTER_DAYS = 7;
// Two quarter ends further apart than a week but closer than a quarter are two
// fiscal calendars (Apple's June quarter, NVIDIA's July one), not a gap.
const OFFSET_CALENDAR_DAYS = 60;

export function pivotTable(table: DisplayTable): ShownTable | null {
  const { keys } = table;
  const name = keys.indexOf("company_name");
  const ticker = keys.indexOf("ticker");
  const end = keys.indexOf("end_date");
  const values = keys.flatMap((key, index) => (key.startsWith("value") ? [index] : []));
  const others = keys.filter((key, index) => ![name, ticker, end, ...values].includes(index));
  if (name < 0 || end < 0 || values.length !== 1 || others.length > 0) return null;
  const value = values[0];
  const company = (row: number) => (ticker >= 0 && table.rows[row][ticker]) || table.rows[row][name] || "";
  const companies = [...new Set(table.rows.map((_, row) => company(row)))];
  if (companies.length < 2 || companies.length === table.rows.length) return null;

  // Quarters newest first, each holding the rows whose end dates sit within a week.
  const dated = table.rows
    .map((_, row) => ({ row, day: table.numbers[row]?.[end] }))
    .filter((item): item is { row: number; day: number } => typeof item.day === "number")
    .sort((a, b) => b.day - a.day);
  if (dated.length !== table.rows.length) return null;
  const quarters: { day: number; rows: number[] }[] = [];
  for (const item of dated) {
    const last = quarters[quarters.length - 1];
    const repeated = last?.rows.find((row) => company(row) === company(item.row));
    // The same company and quarter twice is one cell, not a second row.
    if (repeated !== undefined && table.numbers[repeated]?.[end] === item.day) continue;
    if (last && last.day - item.day <= SAME_QUARTER_DAYS && repeated === undefined) {
      last.rows.push(item.row);
    } else {
      quarters.push({ day: item.day, rows: [item.row] });
    }
  }
  // Companies on different fiscal calendars would leave every row half empty,
  // which reads as missing data: keep the table, each row with its own quarter.
  const daysOf = new Map<string, number[]>();
  for (const { row, day } of dated) daysOf.set(company(row), [...(daysOf.get(company(row)) ?? []), day]);
  const offset = quarters.some((quarter) =>
    companies.some(
      (label) =>
        !quarter.rows.some((row) => company(row) === label) &&
        (daysOf.get(label) ?? []).some(
          (day) => Math.abs(day - quarter.day) > SAME_QUARTER_DAYS && Math.abs(day - quarter.day) < OFFSET_CALENDAR_DAYS,
        ),
    ),
  );
  if (offset) return null;

  const cell = <T>(source: T[][] | undefined, row: number, column: number, empty: T): T =>
    source?.[row]?.[column] ?? empty;
  const shown: ShownTable = {
    headers: [table.headers[end] ?? "Quarter ended", ...companies],
    keys: ["end_date", ...companies.map((label) => `value:${label}`)],
    rows: [],
    numbers: [],
    evidence: [],
    raw: [],
    titles: [],
    row_keys: [],
  };
  for (const quarter of quarters) {
    // The quarter reads as its latest company's end date.
    const lead = quarter.rows.find((row) => table.numbers[row][end] === quarter.day) ?? quarter.rows[0];
    const byCompany = new Map(quarter.rows.map((row) => [company(row), row]));
    const pick = <T>(read: (row: number) => T, empty: T) =>
      companies.map((label) => {
        const row = byCompany.get(label);
        return row === undefined ? empty : read(row);
      });
    shown.rows.push([table.rows[lead][end], ...pick((row) => table.rows[row][value] ?? "", "")]);
    shown.numbers.push([quarter.day, ...pick((row) => table.numbers[row]?.[value] ?? null, null)]);
    shown.evidence?.push([null, ...pick((row) => cell(table.evidence, row, value, null), null)]);
    shown.raw?.push([cell(table.raw, lead, end, ""), ...pick((row) => cell(table.raw, row, value, ""), "")]);
    shown.titles?.push([
      null,
      ...pick((row) => `${table.rows[row][name]}, quarter ended ${table.rows[row][end]}`, null),
    ]);
    shown.row_keys?.push(String(quarter.day));
  }
  return shown;
}
