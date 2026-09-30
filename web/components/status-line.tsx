import { CalendarClock, Database, Radio } from "lucide-react";
import { cn, splitBanner } from "@/lib/format";
import { turnCounterLabel } from "@/lib/turn-state";
import type { RuntimeKind } from "@/lib/types";

/** Snapshot banner, runtime banner, active-analysis chips, and the turn counter. */
export function StatusLine({
  runtime,
  runtimeBanner,
  snapshot,
  chips,
  turns,
}: {
  runtime: RuntimeKind | null;
  /** null while loading; empty when the storefront copy could not be loaded. */
  runtimeBanner: string | null;
  snapshot: { banner: string; stale: boolean } | null;
  chips: string[];
  turns: { count: number; max: number } | null;
}) {
  const RuntimeIcon = runtime === "live" ? Radio : Database;
  // "Live runtime — figures pulled …": the name leads, the detail recedes.
  const [runtimeName, runtimeDetail] = splitBanner(runtimeBanner ?? "");
  return (
    <div className="border-b border-border bg-surface sm:sticky sm:top-14 sm:z-20">
      <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-1.5 text-[11.5px] leading-5 text-subtle sm:flex-row sm:items-center sm:gap-5 sm:px-6">
        {runtimeBanner === null ? (
          <span className="shimmer animate-shimmer h-4 w-72 max-w-full rounded" aria-hidden />
        ) : runtimeBanner === "" ? null : (
          <span className="flex min-w-0 items-start gap-1.5 sm:items-center" title={runtimeBanner}>
            <RuntimeIcon
              className={cn(
                "mt-[3px] size-3.5 shrink-0 sm:mt-0",
                runtime === "live" ? "text-positive" : "text-primary",
              )}
              aria-hidden
            />
            <span className="sm:truncate">
              <span className="font-medium text-muted">{runtimeName}</span>
              {runtimeDetail && <span> · {runtimeDetail}</span>}
            </span>
          </span>
        )}
        {snapshot && (
          <span
            title="Rankings read this dated list of US-listed operating companies; lookups do not need it."
            className={cn(
              "flex w-fit min-w-0 shrink-0 items-start gap-1.5 rounded-md sm:max-w-[45%] sm:items-center",
              snapshot.stale
                ? "border border-warning/30 bg-warning-soft px-1.5 py-0.5 text-warning"
                : "text-subtle",
            )}
          >
            <CalendarClock className="mt-[3px] size-3.5 shrink-0 sm:mt-0" aria-hidden />
            <span className="sm:truncate">{snapshot.banner}</span>
          </span>
        )}
        {turns && (
          <span className="num shrink-0 text-subtle sm:ml-auto" aria-label="Turns used">
            {turnCounterLabel(turns.count, turns.max)}
          </span>
        )}
      </div>
      {chips.length > 0 && (
        <div className="border-t border-border/60">
        <div className="mx-auto flex max-w-6xl items-center gap-2 overflow-x-auto px-4 py-1.5 [scrollbar-width:none] sm:px-6">
          <span className="shrink-0 text-[10px] font-medium uppercase tracking-[0.08em] text-subtle">
            Active analysis
          </span>
          <ul className="flex shrink-0 items-center gap-1.5" aria-label="Active analysis">
            {chips.map((chip) => (
              <li
                key={chip}
                className="rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-[11px] text-fg"
              >
                {chip}
              </li>
            ))}
          </ul>
        </div>
        </div>
      )}
    </div>
  );
}
