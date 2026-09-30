"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, ArrowUpRight, RotateCcw, Table2 } from "lucide-react";
import { useState } from "react";
import { cn, safeHref } from "@/lib/format";
import { nextSort, sortedRowIndices, type TableSort } from "@/lib/table-sort";
import { hasProvenance, tableColumns, type TableColumn, type TableMode } from "@/lib/table-view";
import type { DisplayTable } from "@/lib/types";
import { CopyButton } from "./copy-button";
import { Badge } from "./ui";

const MODES: { mode: TableMode; label: string }[] = [
  { mode: "compact", label: "Compact" },
  { mode: "full", label: "Full" },
];

/**
 * The answer's rows as the server wrote them; the full view adds provenance.
 * A column header sorts the rows; the answer holds the sort so its chart can
 * follow it.
 */
export function DataTable({
  table,
  sort = null,
  onSort,
}: {
  table: DisplayTable;
  sort?: TableSort | null;
  onSort?: (sort: TableSort | null) => void;
}) {
  const [mode, setMode] = useState<TableMode>("compact");
  const columns = tableColumns(table, mode);
  const count = table.rows.length;
  const sortable = Boolean(onSort) && count > 1;
  const order = sortedRowIndices(table, sort);
  const sortedBy = sort ? columns.find((column) => column.key === sort.key)?.header : undefined;
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
        <div className="flex items-center gap-2">
        {sortable && sort && (
          <button
            type="button"
            onClick={() => onSort?.(null)}
            className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[11.5px] font-medium text-muted transition-colors hover:bg-surface-2 hover:text-fg"
            title={sortedBy ? `Sorted by ${sortedBy}` : undefined}
          >
            <RotateCcw className="size-3" aria-hidden />
            Original order
          </button>
        )}
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
        </div>
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
                  aria-sort={
                    sortable && column.kind !== "filing"
                      ? sort?.key === column.key
                        ? sort.direction
                        : "none"
                      : undefined
                  }
                  className={cn(
                    "whitespace-nowrap px-3 py-2 align-bottom text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle first:pl-4 last:pr-4 sm:first:pl-5 sm:last:pr-5",
                    column.numeric ? "text-right" : "text-left",
                    column.kind === "rank" && "w-px pr-1",
                    column.kind === "filing" && "w-px text-right",
                  )}
                >
                  {column.kind === "filing" ? (
                    <span className="sr-only">{column.header}</span>
                  ) : sortable ? (
                    <SortButton
                      column={column}
                      sort={sort}
                      onClick={() => onSort?.(nextSort(table, sort, column.key))}
                    />
                  ) : (
                    <Header column={column} />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {order.map((rowIndex) => table.rows[rowIndex]).map((row, position) => (
              <tr
                key={order[position]}
                className="border-t border-border transition-colors hover:bg-surface-2/50"
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      "whitespace-nowrap px-3 py-2.5 align-middle first:pl-4 last:pr-4 sm:first:pl-5 sm:last:pr-5",
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

function Header({ column }: { column: TableColumn }) {
  return column.kind === "value" ? (
    // A long metric name wraps rather than pushing amounts out of view.
    <span className="inline-block max-w-[6.5rem] whitespace-normal leading-snug">{column.header}</span>
  ) : (
    <>{column.header}</>
  );
}

function SortButton({
  column,
  sort,
  onClick,
}: {
  column: TableColumn;
  sort: TableSort | null;
  onClick: () => void;
}) {
  const active = sort?.key === column.key;
  const Icon = !active ? ArrowUpDown : sort.direction === "ascending" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group -mx-1 inline-flex items-center gap-1 rounded px-1 uppercase tracking-[0.08em] transition-colors hover:text-fg",
        column.numeric && "flex-row-reverse",
        active && "text-fg",
      )}
    >
      <Header column={column} />
      <Icon
        className={cn("size-3 shrink-0", active ? "text-primary" : "opacity-0 group-hover:opacity-60 group-focus-visible:opacity-60")}
        aria-hidden
      />
    </button>
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
          <span className="max-w-[6.5rem] truncate text-fg sm:max-w-[12rem]" title={value}>
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
