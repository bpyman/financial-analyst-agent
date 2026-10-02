"use client";

import { ArrowUp, Loader2 } from "lucide-react";
import {
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type Ref,
} from "react";
import { cn } from "@/lib/format";

/** What the window asks of the question box from outside it. */
export interface ComposerHandle {
  /** Puts a question in the box (an example chip) and focuses it. */
  fill(text: string): void;
  clear(): void;
  focus(): void;
}

/** From this many questions left, the box says how many remain. */
const FEW_TURNS_LEFT = 5;

/**
 * Bottom-pinned question box. Enter sends; Shift+Enter adds a line. It holds
 * its own draft, so typing redraws only the box, not every answer above it.
 */
export function Composer({
  ref,
  onSend,
  busy,
  busyLabel = "Analysis running",
  placeholder,
  maxChars,
  turnsLeft = null,
  lastQuestion = "",
}: {
  ref?: Ref<ComposerHandle>;
  /** Sends a question; false when the window could not take it, so the draft stays. */
  onSend: (message: string) => boolean;
  busy: boolean;
  /** What the send button says while it is busy. */
  busyLabel?: string;
  placeholder: string;
  maxChars: number;
  /** Questions this conversation can still take; null before it has a thread. */
  turnsLeft?: number | null;
  /** The thread's last question: ↑ in an empty box brings it back to edit. */
  lastQuestion?: string;
}) {
  const [value, setValue] = useState("");
  const input = useRef<HTMLTextAreaElement | null>(null);
  const full = turnsLeft !== null && turnsLeft <= 0;
  const canSend = !busy && !full && value.trim().length > 0 && value.length <= maxChars;
  const nearLimit = value.length > maxChars * 0.8;
  const fewLeft = !full && turnsLeft !== null && turnsLeft <= FEW_TURNS_LEFT;

  useImperativeHandle(
    ref,
    () => ({
      fill(text) {
        setValue(text);
        input.current?.focus();
      },
      clear: () => setValue(""),
      focus: () => input.current?.focus(),
    }),
    [],
  );

  useEffect(() => {
    const box = input.current;
    if (!box) return;
    box.style.height = "auto";
    // The CSS max-height (smaller on a short window) caps it and scrolls the rest.
    box.style.height = `${box.scrollHeight}px`;
  }, [value]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (canSend && onSend(value)) setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
      return;
    }
    // Only an empty box: in a draft, ↑ moves the caret as usual.
    if (event.key === "ArrowUp" && !value && lastQuestion && !event.nativeEvent.isComposing) {
      event.preventDefault();
      setValue(lastQuestion);
    }
  }

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-20 bg-gradient-to-t from-bg from-55% to-transparent pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-10 short:pb-2 short:pt-3">
      <form onSubmit={submit} className="pointer-events-auto mx-auto max-w-4xl px-4 sm:px-6 2xl:max-w-5xl min-[1920px]:max-w-6xl">
        <div
          className={cn(
            "flex items-end gap-2 rounded-2xl border border-border-strong bg-surface py-2 pl-4 pr-2 shadow-[0_16px_40px_-20px_rgb(0_0_0/0.5)] transition-[border-color,box-shadow]",
            "focus-within:border-primary/60 focus-within:shadow-[0_0_0_4px_var(--primary-soft),0_16px_40px_-20px_rgb(0_0_0/0.5)]",
            full && "opacity-70",
          )}
        >
          <label htmlFor="composer" className="sr-only">
            Ask a question
          </label>
          <textarea
            id="composer"
            ref={input}
            rows={1}
            value={value}
            disabled={full}
            placeholder={full ? "This conversation is full. Start over to keep asking." : placeholder}
            maxLength={maxChars}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={onKeyDown}
            className="max-h-[180px] min-h-9 flex-1 short:max-h-24 resize-none bg-transparent py-1.5 text-[15px] leading-6 text-fg outline-none placeholder:text-subtle focus-visible:outline-none disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!canSend}
            aria-label={full ? "Conversation full" : busy ? busyLabel : "Send"}
            className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary-solid text-primary-fg shadow-sm shadow-primary/30 transition-[filter,opacity] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-35 disabled:shadow-none"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <ArrowUp className="size-4" aria-hidden />
            )}
          </button>
        </div>
        <div
          className={cn(
            "mt-1.5 flex items-center justify-between gap-3 px-1 text-[11px] text-subtle",
            // A short window keeps the hint row only to warn about a limit.
            !nearLimit && !fewLeft && "short:hidden",
          )}
        >
          {fewLeft ? (
            <span role="status">
              {turnsLeft === 1 ? "1 question left" : `${turnsLeft} questions left`} in this conversation
            </span>
          ) : (
            <>
              <span className="hidden sm:inline">
                <Kbd>Enter</Kbd> to send · <Kbd>Shift</Kbd> + <Kbd>Enter</Kbd> for a new line ·{" "}
                <Kbd>/</Kbd> to ask{lastQuestion ? <> · <Kbd>↑</Kbd> last question</> : null}
              </span>
              <span className="sm:hidden">Answers cite the SEC filing they come from.</span>
            </>
          )}
          {nearLimit && (
            <span
              role={value.length >= maxChars ? "status" : undefined}
              className={cn("num", value.length >= maxChars && "text-warning")}
            >
              {value.length >= maxChars
                ? `Limit reached: questions stop at ${maxChars.toLocaleString("en-US")} characters`
                : `${value.length} / ${maxChars}`}
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
