"use client";

import { CircleHelp, Database, Radio } from "lucide-react";
import { useId, useRef, type ToggleEvent } from "react";
import { cn } from "@/lib/format";
import type { RuntimeGuide as Guide, RuntimeKind } from "@/lib/types";

const PANEL_WIDTH = 352;
const GUTTER = 12;

/**
 * "How runtimes differ": what Recorded and Live each answer from. A native
 * popover, so Escape and a click elsewhere close it; it opens under its button.
 */
export function RuntimeGuide({ guide, runtime }: { guide: Guide; runtime: RuntimeKind | null }) {
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);

  function place(event: ToggleEvent<HTMLDivElement>) {
    if (event.newState !== "open" || !button.current) return;
    const anchor = button.current.getBoundingClientRect();
    const panel = event.currentTarget;
    const width = Math.min(PANEL_WIDTH, window.innerWidth - GUTTER * 2);
    const left = Math.min(Math.max(GUTTER, anchor.left), window.innerWidth - width - GUTTER);
    panel.style.width = `${width}px`;
    panel.style.left = `${left}px`;
    panel.style.top = `${anchor.bottom + 8}px`;
  }

  return (
    <>
      <button
        ref={button}
        type="button"
        popoverTarget={id}
        className="inline-flex shrink-0 items-center gap-1 rounded-md px-1 text-subtle underline-offset-2 transition-colors hover:text-fg hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <CircleHelp className="size-3.5" aria-hidden />
        <span>How runtimes differ</span>
      </button>
      <div
        id={id}
        popover="auto"
        role="dialog"
        aria-label="How runtimes differ"
        onBeforeToggle={place}
        className="fixed inset-auto m-0 max-h-[calc(100dvh-6rem)] overflow-y-auto rounded-xl border border-border-strong bg-surface p-4 text-[12.5px] leading-relaxed text-muted shadow-xl shadow-black/25"
      >
        <div className="space-y-3.5">
          {guide.runtimes.map((item) => {
            const Icon = item.kind === "live" ? Radio : Database;
            const current = item.kind === runtime;
            return (
              <section key={item.kind}>
                <h3 className="flex items-center gap-1.5 text-[13px] font-medium text-fg">
                  <Icon
                    className={cn("size-3.5", item.kind === "live" ? "text-positive" : "text-primary")}
                    aria-hidden
                  />
                  {item.name}
                  {current && (
                    <span className="rounded bg-surface-2 px-1.5 py-px text-[10.5px] font-medium text-subtle">
                      This conversation
                    </span>
                  )}
                </h3>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 marker:text-subtle">
                  {item.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </section>
            );
          })}
          {guide.footer && <p className="border-t border-border pt-3 text-subtle">{guide.footer}</p>}
        </div>
      </div>
    </>
  );
}
