import { answerFileName } from "./answer-text";
import type { DisplayTable } from "./types";

/**
 * An answer table as CSV, in the order on screen: exact amounts where the
 * server sent them (unrounded, no units), the shown text elsewhere. A change
 * column is followed by its percent ("YoY change %"), which its amount alone
 * would not say.
 */
export function tableCsv(table: DisplayTable, rowOrder: number[] | null): string {
  const order = rowOrder ?? table.rows.map((_, index) => index);
  const withPercent = (column: number) =>
    Boolean(table.keys[column]?.startsWith("change:") && table.raw_percent?.some((row) => row[column]));
  const columns = table.headers.flatMap((_, column) =>
    withPercent(column) ? [{ column, percent: false }, { column, percent: true }] : [{ column, percent: false }],
  );
  const lines = [
    columns.map(({ column, percent }) => field(percent ? `${table.headers[column]} %` : table.headers[column])),
    ...order.map((row) =>
      columns.map(({ column, percent }) =>
        field(
          percent
            ? (table.raw_percent?.[row]?.[column] ?? "")
            : (table.raw?.[row]?.[column] ?? table.rows[row]?.[column] ?? ""),
        ),
      ),
    ),
  ];
  return lines.map((line) => line.join(",")).join("\r\n") + "\r\n";
}

const NUMBER = /^-?\d+(\.\d+)?(E-?\d+)?$/i;

/** One field: quoted when it holds a comma, quote or line break; text that a spreadsheet would run as a formula is prefixed. */
function field(value: string): string {
  const safe = /^[=+\-@\t\r]/.test(value) && !NUMBER.test(value) ? `'${value}` : value;
  return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function csvFileName(question: string): string {
  return answerFileName(question).replace(/\.md$/, ".csv");
}
