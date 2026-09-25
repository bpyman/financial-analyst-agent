"use client";

import { X } from "lucide-react";
import { useEffect, useMemo, useReducer, useRef, useState, useSyncExternalStore } from "react";
import {
  ApiError,
  createThread,
  deleteThread,
  getMeta,
  getThread,
  pingHealth,
  runTurn,
} from "@/lib/api";
import {
  THREAD_STORAGE_KEY,
  browserStore,
  resumeThread,
  startOverIfLocked,
  startThread,
  waitForTurn,
  type ThreadApi,
} from "@/lib/thread-session";
import { IDLE, WAKE_AFTER_MS, turnReducer } from "@/lib/turn-state";
import type { Meta, RuntimeKind, ThreadView } from "@/lib/types";
import { Composer } from "./composer";
import { Header } from "./header";
import { Landing } from "./landing";
import { StatusLine } from "./status-line";
import { Thread } from "./thread";
import { Callout } from "./ui";

const threadApi: ThreadApi = { createThread, getThread, deleteThread };
const UNREACHABLE = "The analysis service is unreachable. Please try again shortly.";
const FALLBACK_PLACEHOLDER = "Ask about a company's latest quarterly results…";
const UNFINISHED = "Your last question could not be completed. Please ask it again.";

type Notice = { kind: "info" | "error"; text: string };

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return UNREACHABLE;
}

const subscribeNothing = () => () => {};

/** The audience window: one thread per browser, bound to one runtime (ADR 0006). */
export function AnalystWindow() {
  const store = useMemo(() => browserStore(), []);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [metaWaking, setMetaWaking] = useState(false);
  const [metaAttempt, setMetaAttempt] = useState(0);
  const [view, setView] = useState<ThreadView | null>(null);
  const [chosenRuntime, setChosenRuntime] = useState<RuntimeKind | null>(null);
  const [booted, setBooted] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [turn, dispatch] = useReducer(turnReducer, IDLE);
  const [draft, setDraft] = useState("");
  const [switching, setSwitching] = useState(false);
  const inFlight = useRef(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const shownTurns = useRef(0);

  // Read after hydration only, so the server render and the first client render agree.
  const storedThreadId = useSyncExternalStore(
    subscribeNothing,
    () => store.getItem(THREAD_STORAGE_KEY),
    () => null,
  );

  const runtime: RuntimeKind =
    view?.runtime ?? chosenRuntime ?? (meta && !meta.recorded.default ? "live" : "recorded");
  const locked = meta?.recorded.locked ?? false;
  const busy = turn.status === "running" || switching;

  // Wake on visit, then resume the stored thread. A reload mid-turn finds the
  // turn still in flight: show it running and poll until the answer lands.
  useEffect(() => {
    pingHealth();
    const aborted = new AbortController();
    const { signal } = aborted;

    async function reattach(resumed: ThreadView) {
      inFlight.current = true;
      dispatch({ type: "reattach" });
      try {
        const finished = await waitForTurn(getThread, resumed.thread_id, { signal });
        setView(finished);
        dispatch({ type: "event", event: { event: "thread", data: finished } });
        if (finished.turns.length === resumed.turns.length) {
          setNotice({ kind: "error", text: UNFINISHED });
        }
      } catch (error) {
        if (signal.aborted) return;
        dispatch({ type: "reset" });
        setNotice({ kind: "error", text: errorText(error) });
      } finally {
        inFlight.current = false;
      }
    }

    resumeThread(threadApi, store)
      .then((resumed) => {
        if (signal.aborted) return;
        setView(resumed.view);
        if (resumed.notice) setNotice({ kind: "info", text: resumed.notice });
        if (resumed.view?.turn_in_flight) void reattach(resumed.view);
      })
      .catch((error: unknown) => {
        if (!signal.aborted) setNotice({ kind: "error", text: errorText(error) });
      })
      .finally(() => {
        if (!signal.aborted) setBooted(true);
      });
    return () => aborted.abort();
  }, [store]);

  // A live thread on a deployment locked to the recorded runtime would refuse
  // every turn: Start over on the recorded runtime and say why.
  useEffect(() => {
    if (!locked || view?.runtime !== "live" || inFlight.current) return;
    inFlight.current = true;
    startOverIfLocked(threadApi, store, view, locked)
      .then((started) => {
        if (!started) return;
        shownTurns.current = 0;
        dispatch({ type: "reset" });
        setView(started.view);
        if (started.notice) setNotice({ kind: "info", text: started.notice });
      })
      .catch((error: unknown) => {
        setView(null);
        setNotice({ kind: "error", text: errorText(error) });
      })
      .finally(() => {
        inFlight.current = false;
      });
  }, [locked, view, store]);

  // Storefront copy, and the snapshot banner for the runtime in use.
  useEffect(() => {
    let cancelled = false;
    const waking = window.setTimeout(() => setMetaWaking(true), WAKE_AFTER_MS);
    getMeta(runtime === "recorded")
      .then((loaded) => {
        if (cancelled) return;
        setMeta(loaded);
        setMetaError(null);
      })
      .catch((error: unknown) => {
        if (!cancelled) setMetaError(errorText(error));
      })
      .finally(() => {
        window.clearTimeout(waking);
        if (!cancelled) setMetaWaking(false);
      });
    return () => {
      cancelled = true;
      window.clearTimeout(waking);
    };
  }, [runtime, metaAttempt]);

  // Bring the newest exchange into view: the running turn, or the answer that just landed.
  const turnCount = view?.turns.length ?? 0;
  useEffect(() => {
    const target =
      turn.status !== "idle"
        ? document.querySelector('[data-turn="pending"]')
        : turnCount > shownTurns.current
          ? document.querySelector(`[data-turn="${turnCount - 1}"]`)
          : null;
    shownTurns.current = turnCount;
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [turn.status, turnCount]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || inFlight.current) return;
    inFlight.current = true;
    dispatch({ type: "send", message });
    setDraft("");
    setNotice(null);
    const waking = window.setTimeout(() => dispatch({ type: "wake" }), WAKE_AFTER_MS);
    try {
      let threadId = view?.thread_id;
      if (!threadId) {
        // Before the analyst picks a runtime, the server applies its deployment default.
        const started = await startThread(threadApi, store, chosenRuntime ?? undefined);
        setView(started.view);
        threadId = started.view.thread_id;
        if (started.notice) setNotice({ kind: "info", text: started.notice });
      }
      for await (const event of runTurn(threadId, message)) {
        if (event.event === "thread") setView(event.data);
        dispatch({ type: "event", event });
      }
    } catch (error) {
      dispatch({ type: "fail", error: errorText(error) });
    } finally {
      window.clearTimeout(waking);
      inFlight.current = false;
    }
  }

  /** Start over on `next`: the same runtime, or the other one when the switch flips. */
  async function restart(next: RuntimeKind) {
    if (inFlight.current) return;
    inFlight.current = true;
    setSwitching(true);
    setNotice(null);
    setChosenRuntime(next);
    dispatch({ type: "reset" });
    window.scrollTo({ top: 0 });
    try {
      const previous = view?.thread_id ?? store.getItem(THREAD_STORAGE_KEY);
      const started = await startThread(threadApi, store, next, previous);
      shownTurns.current = 0;
      setView(started.view);
      if (started.notice) setNotice({ kind: "info", text: started.notice });
    } catch (error) {
      setView(null);
      setNotice({ kind: "error", text: errorText(error) });
    } finally {
      inFlight.current = false;
      setSwitching(false);
    }
  }

  function draftQuestion(question: string) {
    setDraft(question);
    inputRef.current?.focus();
  }

  const hasThread = (view?.turns.length ?? 0) > 0 || turn.status !== "idle";
  const resuming = !booted && storedThreadId !== null;

  return (
    <div className="flex min-h-dvh flex-col">
      <Header
        runtime={runtime}
        locked={locked}
        lockedNotice={meta?.runtime_copy.locked ?? ""}
        busy={busy}
        onSwitchRuntime={restart}
        onStartOver={() => restart(runtime)}
      />
      <StatusLine
        runtime={runtime}
        runtimeBanner={meta ? meta.runtime_copy[runtime] : metaError ? "" : null}
        snapshot={meta?.snapshot ?? null}
        chips={view?.spec_chips ?? []}
        turns={view ? { count: view.turn_count, max: view.max_turns } : null}
      />
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-44 sm:px-6">
        {notice && (
          <Callout kind={notice.kind} className="mt-6 animate-fade-up">
            <div className="flex items-start justify-between gap-3">
              <span>{notice.text}</span>
              <button
                type="button"
                onClick={() => setNotice(null)}
                aria-label="Dismiss"
                className="-mr-1 rounded p-0.5 text-subtle hover:text-fg"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>
          </Callout>
        )}
        {resuming ? (
          <ResumeSkeleton />
        ) : hasThread ? (
          <Thread turns={view?.turns ?? []} turn={turn} onRetry={send} onAsk={send} />
        ) : (
          <Landing
            meta={meta}
            waking={metaWaking}
            error={metaError}
            disabled={busy}
            onAsk={send}
            onDraft={draftQuestion}
            onRetry={() => setMetaAttempt((attempt) => attempt + 1)}
          />
        )}
      </main>
      <Composer
        value={draft}
        onChange={setDraft}
        onSend={send}
        busy={busy}
        placeholder={meta?.example_query ?? FALLBACK_PLACEHOLDER}
        maxChars={meta?.max_message_chars ?? 2000}
        inputRef={inputRef}
      />
    </div>
  );
}

function ResumeSkeleton() {
  return (
    <div className="space-y-5 pt-10" aria-busy="true" aria-label="Loading your thread">
      <div className="flex justify-end">
        <div className="shimmer animate-shimmer h-10 w-2/3 max-w-md rounded-2xl" />
      </div>
      <div className="shimmer animate-shimmer h-56 w-full rounded-2xl" />
      <div className="shimmer animate-shimmer h-32 w-full rounded-xl" />
    </div>
  );
}
