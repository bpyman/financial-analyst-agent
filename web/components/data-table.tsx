"use client";

import { ArrowUpRight, Table2 } from "lucide-react";
import { useState } from "react";
import { cn, safeHref } from "@/lib/format";
import { hasProvenance, tableColumns, type TableColumn, type TableMode } from "@/lib/table-view";
import type { DisplayTable } from "@/lib/types";
import { CopyButton } from "./copy-button";
import { Badge } from "./ui";

const MODES: { mode: TableMode; label: string }[] = [
  { mode: "compact", label: "Compact" },
  { mode: "full", label: "Full" },
];

/** The answer's rows as the server wrote them; the full view adds provenance. */
export function DataTable({ table }: { table: DisplayTable }) {
  const [mode, setMode] = useState<TableMode>("compact");
  const columns = tableColumns(table, mode);
  const count = table.rows.length;
  return (
    <section aria-label="Answer table" className="overflow-hidden rounded-xl border border-border bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2 text-[13px] font-medium text-fg">
          <Table2 className="size-4 text-primary" aria-hidden />
          Table
          <span className="text-[11px] font-normal tabular-nums text-subtle">
            {count === 1 ? "1 row" : `${count} rows`}
          </span>
        </div>
        {hasProvenance(table) && (
          <div
            role="radiogroup"
            aria-label="Table columns"
            className="flex h-7 items-center rounded-lg border border-border bg-surface-2 p-0.5"
          >
            {MODES.map(({ mode: option, label }) => {
              const active = option === mode;
              return (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setMode(option)}
                  className={cn(
                    "inline-flex h-full items-center rounded-md px-2.5 text-[11.5px] font-medium transition-colors",
                    active ? "bg-surface text-fg shadow-sm ring-1 ring-border-strong" : "text-muted hover:text-fg",
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        )}
      </header>
      {/* relative: keeps sr-only text inside the scroller instead of widening the page. */}
      <div className="relative overflow-x-auto overscroll-x-contain">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="bg-surface-2/50">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cn(
                    "whitespace-nowrap px-4 py-2 text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle first:pl-4 sm:first:pl-5",
                    column.numeric ? "text-right" : "text-left",
                    column.kind === "rank" && "w-px pr-1",
                    column.kind === "filing" && "w-px text-right",
                  )}
                >
                  {column.kind === "filing" ? (
                    <span className="sr-only">{column.header}</span>
                  ) : column.kind === "value" ? (
                    // A long metric name wraps rather than pushing amounts off a phone screen.
                    <span className="inline-block max-w-[7.5rem] whitespace-normal leading-snug sm:max-w-none sm:whitespace-nowrap">
                      {column.header}
                    </span>
                  ) : (
                    column.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className="border-t border-border transition-colors hover:bg-surface-2/50"
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      "whitespace-nowrap px-4 py-2.5 align-middle first:pl-4 sm:first:pl-5",
                      column.numeric && "text-right",
                      column.kind === "rank" && "pr-1",
                      column.kind === "filing" && "text-right",
                    )}
                  >
                    <Cell column={column} row={row} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Cell({ column, row }: { column: TableColumn; row: string[] }) {
  const value = row[column.index] ?? "";
  switch (column.kind) {
    case "rank":
      return <span className="num text-subtle">{value}</span>;
    case "company": {
      const ticker = column.tickerIndex === undefined ? "" : row[column.tickerIndex];
      return (
        <span className="flex min-w-0 items-center gap-2.5">
          {ticker ? (
            <span className="num inline-flex h-5 min-w-11 shrink-0 items-center justify-center rounded border border-border-strong bg-surface-2 px-1.5 text-[10.5px] font-semibold text-fg">
              {ticker}
            </span>
          ) : (
            // Keeps names aligned when a row has no ticker.
            column.tickerIndex !== undefined && <span aria-hidden className="w-11 shrink-0" />
          )}
          <span className="max-w-[6.5rem] truncate text-fg sm:max-w-[14rem]" title={value}>
            {value}
          </span>
        </span>
      );
    }
    case "value":
      return value ? (
        <span className="font-medium tabular-nums text-fg">{value}</span>
      ) : (
        <span className="text-subtle" aria-label="No value">
          —
        </span>
      );
    case "date":
      return <span className="tabular-nums text-muted">{value}</span>;
    case "identifier":
      return value ? (
        <span className="inline-flex items-center gap-0.5">
          <span className="num text-muted">{value}</span>
          <CopyButton value={value} label={column.header} />
        </span>
      ) : null;
    case "code":
      return (
        <span className="num block max-w-[18rem] truncate text-[12px] text-muted" title={value}>
          {value}
        </span>
      );
    case "reason":
      return value ? <Badge tone="warning">{value}</Badge> : null;
    case "filing":
      return safeHref(value) ? (
        <a
          href={value}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-0.5 rounded text-xs font-medium text-primary underline-offset-4 hover:underline"
        >
          Filing
          <ArrowUpRight className="size-3.5" aria-hidden />
        </a>
      ) : null;
    default:
      return <span className="text-fg">{value}</span>;
  }
}
