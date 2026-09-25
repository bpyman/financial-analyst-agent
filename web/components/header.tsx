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
        <Link href="/" className="flex min-w-0 items-center gap-2.5" aria-label="Financial analyst agent">
          <LogoMark className="size-7 shrink-0" />
          <span className="hidden min-w-0 flex-col leading-tight sm:flex">
            <span className="truncate text-sm font-semibold tracking-tight">Financial analyst agent</span>
            <span className="truncate text-[11px] text-subtle">SEC 10-Q evidence, traced to the filing</span>
          </span>
        </Link>
        <div className="ml-auto flex items-center gap-2">
          <RuntimeSwitch
            runtime={runtime}
            locked={locked}
            lockedNotice={lockedNotice}
            disabled={busy}
            onChange={onSwitchRuntime}
          />
          <ThemeToggle />
          <button
            type="button"
            onClick={onStartOver}
            disabled={busy}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface px-2 text-xs font-medium text-fg transition-colors hover:border-border-strong hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50 sm:px-3"
          >
            <RotateCcw className="size-3.5" aria-hidden />
            <span className="sr-only sm:not-sr-only">Start over</span>
          </button>
        </div>
      </div>
    </header>
  );
}

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
  { value: "system", label: "System theme", Icon: Monitor },
  { value: "light", label: "Light theme", Icon: Sun },
  { value: "dark", label: "Dark theme", Icon: Moon },
] as const;

const subscribeNothing = () => () => {};

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  // next-themes only knows the stored theme after hydration.
  const mounted = useSyncExternalStore(subscribeNothing, () => true, () => false);
  const current = mounted ? (theme ?? "dark") : null;
  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="flex h-8 items-center rounded-lg border border-border bg-surface-2 p-0.5"
    >
      {THEMES.map(({ value, label, Icon }) => {
        const active = current === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={cn(
              "inline-flex h-full w-7 items-center justify-center rounded-md transition-colors",
              active
                ? "bg-surface text-fg shadow-sm ring-1 ring-border-strong"
                : "text-subtle hover:text-fg",
            )}
          >
            <Icon className="size-3.5" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}
