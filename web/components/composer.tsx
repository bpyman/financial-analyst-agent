"use client";

import { ArrowUp, Loader2 } from "lucide-react";
import { useEffect, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { cn } from "@/lib/format";

/** Bottom-pinned question box. Enter sends; Shift+Enter adds a line. */
export function Composer({
  value,
  onChange,
  onSend,
  busy,
  placeholder,
  maxChars,
  inputRef,
}: {
  value: string;
  onChange: (value: string) => void;
  onSend: (message: string) => void;
  busy: boolean;
  placeholder: string;
  maxChars: number;
  inputRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const canSend = !busy && value.trim().length > 0 && value.length <= maxChars;
  const nearLimit = value.length > maxChars * 0.8;

  useEffect(() => {
    const box = inputRef.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 180)}px`;
  }, [value, inputRef]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (canSend) onSend(value);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-20 bg-gradient-to-t from-bg from-55% to-transparent pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-10">
      <form onSubmit={submit} className="pointer-events-auto mx-auto max-w-4xl px-4 sm:px-6">
        <div
          className={cn(
            "flex items-end gap-2 rounded-2xl border border-border-strong bg-surface py-2 pl-4 pr-2 shadow-[0_16px_40px_-20px_rgb(0_0_0/0.5)] transition-[border-color,box-shadow]",
            "focus-within:border-primary/60 focus-within:shadow-[0_0_0_4px_var(--primary-soft),0_16px_40px_-20px_rgb(0_0_0/0.5)]",
          )}
        >
          <label htmlFor="composer" className="sr-only">
            Ask a question
          </label>
          <textarea
            id="composer"
            ref={inputRef}
            rows={1}
            value={value}
            placeholder={placeholder}
            maxLength={maxChars}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={onKeyDown}
            className="max-h-[180px] min-h-9 flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-6 text-fg outline-none placeholder:text-subtle focus-visible:outline-none"
          />
          <button
            type="submit"
            disabled={!canSend}
            aria-label={busy ? "Analysis running" : "Send"}
            className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-fg shadow-sm shadow-primary/30 transition-[filter,opacity] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-35 disabled:shadow-none"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <ArrowUp className="size-4" aria-hidden />
            )}
          </button>
        </div>
        <div className="mt-1.5 flex items-center justify-between gap-3 px-1 text-[11px] text-subtle">
          <span className="hidden sm:inline">
            <Kbd>Enter</Kbd> to send · <Kbd>Shift</Kbd> + <Kbd>Enter</Kbd> for a new line
          </span>
          <span className="sm:hidden">Answers cite the SEC filing they come from.</span>
          {nearLimit && (
            <span className={cn("num", value.length >= maxChars && "text-warning")}>
              {value.length} / {maxChars}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}

function Kbd({ children }: { children: string }) {
  return (
    <kbd className="rounded border border-border bg-surface-2 px-1 py-px font-sans text-[10px] text-muted">
      {children}
    </kbd>
  );
}
