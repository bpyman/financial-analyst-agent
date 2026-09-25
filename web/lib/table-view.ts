import type { DisplayTable } from "./types";

/**
 * Which of the server's table columns to draw, and how. Cells stay the
 * server's strings (ADR 0006); this only picks, orders, and styles columns.
 */
export type ColumnKind =
  | "rank"
  | "company"
  | "value"
  | "date"
  | "identifier"
  | "code"
  | "reason"
  | "filing"
  | "text";

export interface TableColumn {
  key: string;
  header: string;
  /** Index into each server row. */
  index: number;
  kind: ColumnKind;
  /** Right-aligned tabular numerals. */
  numeric: boolean;
  /** A company column that also shows the row's ticker. */
  tickerIndex?: number;
}

export type TableMode = "compact" | "full";

/** Provenance only the full view shows: identifiers, currency, and filing details. */
const PROVENANCE = new Set([
  "cik",
  "currency",
  "start_date",
  "form",
  "accession_number",
  "taxonomy",
  "concept",
]);

const KIND: Record<string, ColumnKind> = {
  rank: "rank",
  company_name: "company",
  value: "value",
  start_date: "date",
  end_date: "date",
  cik: "identifier",
  accession_number: "identifier",
  concept: "code",
  taxonomy: "code",
  form: "code",
  reason: "reason",
  source_url: "filing",
};

export function tableColumns(table: DisplayTable, mode: TableMode): TableColumn[] {
  const { keys, headers } = table;
  const tickerIndex = keys.indexOf("ticker");
  const merged = tickerIndex >= 0 && keys.includes("company_name");
  const columns: TableColumn[] = [];
  keys.forEach((key, index) => {
    if (merged && key === "ticker") return;
    if (mode === "compact" && PROVENANCE.has(key)) return;
    const kind = KIND[key] ?? "text";
    columns.push({
      key,
      header: headers[index] ?? key,
      index,
      kind,
      numeric: kind === "rank" || kind === "value",
      ...(kind === "company" && merged ? { tickerIndex } : {}),
    });
  });
  // The filing link closes each row, where the eye lands after the numbers.
  const filing = columns.findIndex((column) => column.kind === "filing");
  if (filing >= 0) columns.push(...columns.splice(filing, 1));
  return columns;
}

/** Whether the full view adds anything over the compact one. */
export function hasProvenance(table: DisplayTable): boolean {
  return table.keys.some((key) => PROVENANCE.has(key));
}
