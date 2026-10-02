"use client";

import { RotateCcw } from "lucide-react";
import { Button, LogoMark } from "@/components/ui";
import { THREAD_STORAGE_KEY, browserStore } from "@/lib/browser-thread";

/**
 * The page failed to draw. The saved conversation is the likely cause, and a
 * reload would resume it and fail again, so the way out forgets it first.
 */
export default function PageError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  function startFresh() {
    browserStore().removeItem(THREAD_STORAGE_KEY);
    window.location.reload();
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-5 px-4">
      <LogoMark className="size-10" />
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-fg">This page couldn&apos;t be shown</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          Something in your saved conversation could not be displayed. Starting a new conversation
          clears it from this browser.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={startFresh}>
          <RotateCcw className="size-4" aria-hidden />
          Start a new conversation
        </Button>
        <Button variant="outline" onClick={() => retry()}>
          Try again
        </Button>
      </div>
    </main>
  );
}
