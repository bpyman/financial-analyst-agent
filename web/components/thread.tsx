"use client";

import { Loader2, RotateCw } from "lucide-react";
import type { ReactNode } from "react";
import { clarifyChoices, shownMessage } from "@/lib/clarify";
import { progressLabel, type TurnState } from "@/lib/turn-state";
import type { Turn } from "@/lib/types";
import { Answer } from "./answer";
import { Button, Callout, LogoMark } from "./ui";

/** The conversation: finished turns, then the running or failed one. */
export function Thread({
  turns,
  turn,
  onRetry,
  onAsk,
}: {
  turns: Turn[];
  turn: TurnState;
  onRetry: (message: string) => void;
  /** Sends a clarify candidate's slug as the next analyst message. */
  onAsk: (message: string) => void;
}) {
  const running = turn.status === "running";
  return (
    <ol className="space-y-12 pt-8 sm:pt-10" aria-label="Conversation">
      {turns.map((item, index) => (
        <li
          key={item.index}
          data-turn={index}
          className="scroll-mt-20 sm:scroll-mt-40"
        >
          <Exchange message={shownMessage(item, turns[index - 1])} sent={item.message}>
            <Answer
              presentation={item.presentation}
              clarify={{
                choices: clarifyChoices(item, turns[index + 1]),
                live: item.clarify_enabled && !running,
                onChoose: onAsk,
              }}
            />
          </Exchange>
        </li>
      ))}
      {turn.status === "running" && (
        <li data-turn="pending" className="scroll-mt-20 sm:scroll-mt-40">
          <Exchange message={shownMessage(turn, turns.at(-1))} sent={turn.message} working>
            <Working state={turn} />
          </Exchange>
        </li>
      )}
      {turn.status === "failed" && (
        <li data-turn="pending" className="scroll-mt-20 sm:scroll-mt-40">
          <Exchange message={shownMessage(turn, turns.at(-1))} sent={turn.message}>
            <Callout kind="error">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span>{turn.error}</span>
                <Button size="sm" variant="outline" onClick={() => onRetry(turn.message)}>
                  <RotateCw className="size-3.5" aria-hidden />
                  Try again
                </Button>
              </div>
            </Callout>
          </Exchange>
        </li>
      )}
    </ol>
  );
}

function Exchange({
  message,
  sent,
  working = false,
  children,
}: {
  message: string;
  /** The message as sent, when the thread shows it differently (a clarify slug). */
  sent?: string;
  working?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="animate-fade-up">
      <div className="flex justify-end">
        <p
          title={sent && sent !== message ? `Sent as ${sent}` : undefined}
          className="max-w-[88%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md border border-border bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed text-fg sm:max-w-[75%]">
          {message}
        </p>
      </div>
      <div className="mt-5 flex gap-3">
        <div className="relative hidden shrink-0 sm:block">
          <LogoMark className="size-7" />
          {working && (
            <span aria-hidden className="absolute -right-0.5 -top-0.5 flex size-2.5">
              <span className="absolute inset-0 animate-ping rounded-full bg-primary/60" />
              <span className="relative size-2.5 rounded-full bg-primary ring-2 ring-bg" />
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}

function Working({ state }: { state: Extract<TurnState, { status: "running" }> }) {
  const { progress, waking } = state;
  const fraction =
    progress && progress.total > 0 ? Math.min(1, progress.done / progress.total) : null;
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <div className="px-4 py-3.5" role="status" aria-live="polite">
        <div className="flex items-center gap-2 text-[13px] font-medium text-fg">
          <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
          {progressLabel(state)}
        </div>
        {waking && (
          <p className="mt-1 pl-6 text-xs text-muted">
            The hosted service sleeps when idle and takes about a minute to wake.
          </p>
        )}
      </div>
      <div className="h-0.5 bg-surface-3" aria-hidden>
        {fraction === null ? (
          <div className="h-full w-1/3 animate-[indeterminate_1.4s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-primary to-transparent" />
        ) : (
          <div
            className="h-full bg-primary transition-[width] duration-300"
            style={{ width: `${Math.max(fraction * 100, 4)}%` }}
          />
        )}
      </div>
      <div className="space-y-3 px-4 py-4" aria-hidden>
        <div className="shimmer animate-shimmer h-3 w-24 rounded" />
        <div className="shimmer animate-shimmer h-9 w-48 rounded-md" />
        <div className="shimmer animate-shimmer h-3 w-64 max-w-full rounded" />
      </div>
    </div>
  );
}
