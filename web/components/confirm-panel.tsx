"use client";

import { useEffect, useId, useRef } from "react";

export interface ConfirmRequest {
  title: string;
  body: string;
  /** The button that goes ahead, named for what it does. */
  action: string;
}

/**
 * Asks before a conversation is cleared, in the page rather than with
 * `window.confirm`: in-app browsers (LinkedIn, Slack) answer that with Cancel
 * without showing it, so Start over did nothing there. Escape or a click
 * elsewhere cancels. Focus starts on Cancel, the safe answer, stays inside
 * while it is open, and goes back to what opened it.
 */
export function ConfirmPanel({
  request,
  onConfirm,
  onCancel,
}: {
  request: ConfirmRequest;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const bodyId = useId();
  const panel = useRef<HTMLDivElement | null>(null);
  const cancelButton = useRef<HTMLButtonElement | null>(null);
  const cancel = useRef(onCancel);
  useEffect(() => {
    cancel.current = onCancel;
  });

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    cancelButton.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Handled here: the window's own Escape (dismissing a notice) checks this.
        event.preventDefault();
        cancel.current();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const buttons = [...panel.current.querySelectorAll<HTMLElement>("button")];
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      const inside = panel.current.contains(document.activeElement);
      if (event.shiftKey && (document.activeElement === first || !inside)) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !inside)) {
        event.preventDefault();
        first?.focus();
      }
    };
    const onPointer = (event: PointerEvent) => {
      if (!panel.current?.contains(event.target as Node)) cancel.current();
    };
    // Capture, so this runs before any other Escape listener on the window.
    window.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onPointer);
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  return (
    <div
      ref={panel}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      // Fixed, so it shows wherever the page is scrolled; lined up with the header's right edge.
      className="fixed right-4 top-[4.25rem] z-40 w-[min(20rem,calc(100vw-2rem))] animate-fade-up rounded-xl border border-border-strong bg-surface p-4 shadow-lg shadow-black/20 sm:right-[max(1.5rem,calc((100vw-56rem)/2+1.5rem))]"
    >
      <p id={titleId} className="text-sm font-medium text-fg">
        {request.title}
      </p>
      <p id={bodyId} className="mt-1 text-sm text-muted">
        {request.body}
      </p>
      <div className="mt-4 flex justify-end gap-2">
        <button
          ref={cancelButton}
          type="button"
          onClick={onCancel}
          className="inline-flex h-8 items-center rounded-lg px-3 text-xs font-medium text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="inline-flex h-8 items-center rounded-lg bg-primary-solid px-3 text-xs font-medium text-primary-fg shadow-sm shadow-primary/30 transition-[filter] hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
        >
          {request.action}
        </button>
      </div>
    </div>
  );
}
