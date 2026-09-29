"use client";

import { Lock, Monitor, Moon, RotateCcw, Sun } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useId, useSyncExternalStore } from "react";
import { cn } from "@/lib/format";
import type { RuntimeKind } from "@/lib/types";
import { LogoMark } from "./ui";

const RUNTIMES: { kind: RuntimeKind; label: string }[] = [
  { kind: "recorded", label: "Recorded" },
  { kind: "live", label: "Live" },
];

export function Header({
  runtime,
  locked,
  lockedNotice,
  busy,
  onSwitchRuntime,
  onStartOver,
}: {
  runtime: RuntimeKind;
  locked: boolean;
  lockedNotice: string;
  busy: boolean;
  onSwitchRuntime: (runtime: RuntimeKind) => void;
  onStartOver: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-bg">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:px-6">
        <Link
          href="/"
          className="flex min-w-0 items-center gap-2.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-primary"
          aria-label="Onfile"
        >
          <LogoMark className="size-8 shrink-0" />
          <span className="text-[17px] font-semibold leading-none tracking-[-0.02em] text-fg">Onfile</span>
          {/* One line beside the name, not a caption under it: a short name reads as the lead. */}
          <span aria-hidden className="ml-1 hidden h-4 w-px shrink-0 bg-border-strong lg:block" />
          <span className="hidden truncate text-[13px] text-subtle lg:block">
            SEC 10-Q evidence, traced to the filing
          </span>
        </Link>
        <div className="ml-auto flex items-center gap-1 sm:gap-1.5">
          <RuntimeSwitch
            runtime={runtime}
            locked={locked}
            lockedNotice={lockedNotice}
            disabled={busy}
            onChange={onSwitchRuntime}
          />
          <span aria-hidden className="mx-1 hidden h-5 w-px bg-border sm:block" />
          <ThemeToggle />
          <button
            type="button"
            onClick={onStartOver}
            disabled={busy}
            title="Start over"
            className={cn(GHOST_BUTTON, "gap-1.5 px-2 sm:px-2.5")}
          >
            <RotateCcw className="size-3.5" aria-hidden />
            <span className="sr-only sm:not-sr-only">Start over</span>
          </button>
        </div>
      </div>
    </header>
  );
}

// Utilities sit quietly beside the one bordered control, the runtime switch.
const GHOST_BUTTON =
  "inline-flex h-8 items-center justify-center rounded-lg text-xs font-medium text-muted transition-colors " +
  "hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary " +
  "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-muted";

function RuntimeSwitch({
  runtime,
  locked,
  lockedNotice,
  disabled,
  onChange,
}: {
  runtime: RuntimeKind;
  locked: boolean;
  lockedNotice: string;
  disabled: boolean;
  onChange: (runtime: RuntimeKind) => void;
}) {
  const tooltipId = useId();
  const group = (
    <div
      role="radiogroup"
      aria-label="Runtime"
      aria-describedby={locked ? tooltipId : undefined}
      className={cn(
        "relative flex h-8 items-center rounded-lg border border-border bg-surface-2 p-0.5",
        locked && "opacity-80",
      )}
    >
      {locked && <Lock className="mx-1.5 size-3 text-subtle" aria-hidden />}
      {RUNTIMES.map(({ kind, label }) => {
        const active = kind === runtime;
        return (
          <button
            key={kind}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={locked || disabled || active}
            onClick={() => onChange(kind)}
            className={cn(
              "inline-flex h-full items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
              active
                ? "bg-surface text-fg shadow-sm ring-1 ring-border-strong"
                : "text-muted hover:text-fg disabled:hover:text-muted",
              !active && (locked || disabled) && "cursor-not-allowed",
              active && "cursor-default",
            )}
          >
            <span
              aria-hidden
              className={cn(
                "size-1.5 rounded-full",
                !active
                  ? "bg-subtle/50"
                  : kind === "live"
                    ? "bg-positive shadow-[0_0_0_3px] shadow-positive/20"
                    : "bg-primary shadow-[0_0_0_3px] shadow-primary/20",
              )}
            />
            {label}
          </button>
        );
      })}
    </div>
  );
  if (!locked) return group;
  return (
    <span tabIndex={0} className="group/tip relative rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-primary">
      {group}
      <span
        id={tooltipId}
        role="tooltip"
        className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-40 w-max max-w-[16rem] translate-y-1 rounded-lg border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-fg opacity-0 shadow-lg shadow-black/20 transition duration-150 group-hover/tip:translate-y-0 group-hover/tip:opacity-100 group-focus-visible/tip:translate-y-0 group-focus-visible/tip:opacity-100"
      >
        <span className="flex items-center gap-1.5">
          <Lock className="size-3 text-warning" aria-hidden />
          {lockedNotice}
        </span>
      </span>
    </span>
  );
}

const THEMES = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
] as const;

const subscribeNothing = () => () => {};

/** One button that steps System → Light → Dark; its icon shows the current choice. */
function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  // next-themes only knows the stored theme after hydration.
  const mounted = useSyncExternalStore(subscribeNothing, () => true, () => false);
  const index = Math.max(0, THEMES.findIndex(({ value }) => value === (theme ?? "dark")));
  const current = THEMES[index];
  const next = THEMES[(index + 1) % THEMES.length];
  const label = `Theme: ${current.label}. Switch to ${next.label.toLowerCase()}`;
  return (
    <button
      type="button"
      onClick={() => setTheme(next.value)}
      aria-label={label}
      title={label}
      className={cn(GHOST_BUTTON, "w-8", !mounted && "invisible")}
    >
      <current.Icon className="size-4" aria-hidden />
    </button>
  );
}
