// One thread per browser (ADR 0006): the id lives in local storage so a reload
// resumes it; Start over and a runtime switch replace it with a new one.

import { ApiError } from "./api";
import type { CreatedThread, RuntimeKind, ThreadView, TurnEvent } from "./types";

export const THREAD_STORAGE_KEY = "financial-analyst-agent.thread-id";
export const EXPIRED_NOTICE = "Your previous thread has expired, so this is a fresh start.";
export const LOCKED_LIVE_NOTICE =
  "Live runtime is off on this deployment, so your live thread was replaced with a fresh start on the recorded runtime.";
export const TURN_WAIT_TIMEOUT =
  "Your last question is taking too long to finish. Please try again shortly.";

/** "in about 10 minutes": when a limit the server named lifts. */
export function waitPhrase(seconds: number | null): string {
  if (seconds === null) return "in a little while";
  if (seconds < 45) return `in ${Math.max(1, Math.round(seconds))} seconds`;
  if (seconds < 90) return "in about a minute";
  if (seconds < 5400) return `in about ${Math.round(seconds / 60)} minutes`;
  return `in about ${Math.round(seconds / 3600)} hours`;
}

export function threadLimitText(seconds: number | null): string {
  return `You've started a lot of new conversations in the last hour, so another can't start yet. Try again ${waitPhrase(seconds)}.`;
}

export function questionLimitText(seconds: number | null): string {
  return `You've asked a lot of questions in the last hour. You can ask again ${waitPhrase(seconds)}.`;
}

/** The thread this window asked on was replaced by another tab's Start over. */
export class ThreadMovedError extends Error {
  constructor(readonly threadId: string) {
    super("This conversation changed in another tab.");
  }
}

export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface ThreadApi {
  createThread(runtime?: RuntimeKind): Promise<CreatedThread>;
  getThread(threadId: string): Promise<ThreadView>;
  deleteThread(threadId: string): Promise<void>;
}

export function memoryStore(initial: Record<string, string> = {}): KeyValueStore {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => void values.set(key, value),
    removeItem: (key) => void values.delete(key),
  };
}

/** `localStorage` when the browser allows it; otherwise memory for this tab only. */
export function browserStore(): KeyValueStore {
  const fallback = memoryStore();
  const attempt = <T>(withStorage: (storage: Storage) => T, orElse: () => T): T => {
    try {
      return withStorage(window.localStorage);
    } catch {
      return orElse();
    }
  };
  return {
    getItem: (key) => attempt((s) => s.getItem(key), () => fallback.getItem(key)),
    setItem: (key, value) => attempt((s) => s.setItem(key, value), () => fallback.setItem(key, value)),
    removeItem: (key) => attempt((s) => s.removeItem(key), () => fallback.removeItem(key)),
  };
}

export interface ThreadOutcome<V> {
  view: V;
  /** A quiet line for the analyst: an expired thread, or a runtime the deploy overrode. */
  notice: string | null;
}

/** Whether `threadId` is still this browser's thread, not one Start over replaced. */
export function isCurrentThread(store: KeyValueStore, threadId: string): boolean {
  return store.getItem(THREAD_STORAGE_KEY) === threadId;
}

/** The server mints UUIDs; anything else in storage (a "/" included) cannot name a thread. */
export function plausibleThreadId(threadId: string): boolean {
  return /^[A-Za-z0-9_-]{1,128}$/.test(threadId);
}

/**
 * The stored thread, if the server still has it. A thread that comes back
 * unknown or empty has expired (TTL or a restarted host): it is forgotten and
 * the analyst is told. An outage rethrows and keeps the id for a retry.
 * `null` when the stored thread changed while it loaded (Start over, or a new
 * thread): the answer is stale and must not replace the one in use.
 */
export async function resumeThread(
  api: ThreadApi,
  store: KeyValueStore,
): Promise<ThreadOutcome<ThreadView | null> | null> {
  const threadId = store.getItem(THREAD_STORAGE_KEY);
  if (!threadId) return { view: null, notice: null };
  if (!plausibleThreadId(threadId)) return forget(store);
  let view: ThreadView;
  try {
    view = await api.getThread(threadId);
  } catch (error) {
    if (!isCurrentThread(store, threadId)) return null;
    if (error instanceof ApiError && [400, 404, 405, 414, 431].includes(error.status)) return forget(store);
    throw error;
  }
  if (!isCurrentThread(store, threadId)) return null;
  if (view.runtime === null && view.turns.length === 0) return forget(store);
  return { view, notice: null };
}

function forget(store: KeyValueStore): ThreadOutcome<null> {
  store.removeItem(THREAD_STORAGE_KEY);
  return { view: null, notice: EXPIRED_NOTICE };
}

/**
 * Start a new thread bound to `runtime`, then clear `previousId`. Start over
 * is this on the same runtime; switching runtime is this on the other.
 * `undefined` leaves the runtime to the deployment default (the analyst has
 * not chosen one). The new thread is made first, so a refusal (the hourly
 * limit, an outage) leaves the current conversation where it was.
 */
export async function startThread(
  api: ThreadApi,
  store: KeyValueStore,
  runtime: RuntimeKind | undefined,
  previousId?: string | null,
): Promise<ThreadOutcome<ThreadView>> {
  let created: CreatedThread;
  try {
    created = await api.createThread(runtime);
  } catch (error) {
    // The server's limit copy is about questions; this one is about conversations.
    if (error instanceof ApiError && error.status === 429) {
      throw new ApiError(threadLimitText(error.retryAfter), 429, error.retryAfter);
    }
    throw error;
  }
  const view = await api.getThread(created.thread_id);
  store.setItem(THREAD_STORAGE_KEY, created.thread_id);
  if (previousId && previousId !== created.thread_id) {
    try {
      await api.deleteThread(previousId);
    } catch {
      // Best effort: the old thread expires on its own.
    }
  }
  return { view, notice: created.notice };
}

/**
 * Ask `message` on `threadId`, yielding the turn's events. The server refuses
 * (404) a turn on a thread it no longer has, before anything runs: it expired,
 * or the host restarted, while the window sat open. Then start a fresh thread
 * on `runtime`, hand it to `onFresh`, and ask there instead, once. When
 * another tab's Start over is why, follow that tab's thread instead
 * (`ThreadMovedError`) rather than start a third one over it.
 */
export async function* askOnThread(
  api: ThreadApi,
  store: KeyValueStore,
  runTurn: (threadId: string, message: string) => AsyncIterable<TurnEvent>,
  threadId: string,
  message: string,
  runtime: RuntimeKind | undefined,
  onFresh: (started: ThreadOutcome<ThreadView>) => void,
): AsyncGenerator<TurnEvent> {
  try {
    yield* runTurn(threadId, message);
    return;
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404)) throw error;
  }
  const stored = store.getItem(THREAD_STORAGE_KEY);
  if (stored && stored !== threadId && plausibleThreadId(stored)) throw new ThreadMovedError(stored);
  const started = await startThread(api, store, runtime);
  onFresh({ view: started.view, notice: started.notice ?? EXPIRED_NOTICE });
  yield* runTurn(started.view.thread_id, message);
}

/**
 * A thread bound to the live runtime cannot take a turn on a deployment locked
 * to the recorded runtime (a preview talking to the public demo), so Start over
 * on the recorded runtime and say why. `null` when the thread can stay.
 */
export async function startOverIfLocked(
  api: ThreadApi,
  store: KeyValueStore,
  view: ThreadView | null,
  locked: boolean,
): Promise<ThreadOutcome<ThreadView> | null> {
  if (!locked || view?.runtime !== "live") return null;
  const started = await startThread(api, store, "recorded", view.thread_id);
  return { view: started.view, notice: LOCKED_LIVE_NOTICE };
}

export interface WaitOptions {
  sleep?: (ms: number) => Promise<void>;
  firstDelayMs?: number;
  maxDelayMs?: number;
  /** Stop waiting after this long in total and report the turn as stuck. */
  maxWaitMs?: number;
  signal?: AbortSignal;
}

const pause = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** A busy server asks for seconds; a longer wait is the visitor's own hourly limit. */
const BUSY_RETRY_MAX_SECONDS = 15;

/**
 * Run a turn, and while the server is busy (every turn slot taken) wait the
 * seconds it asks and try again, up to ``maxWaitMs`` in all. A spike of
 * visitors then queues for a slot instead of each seeing an error.
 */
export async function* whenFree(
  run: () => AsyncIterable<TurnEvent>,
  {
    onBusy,
    sleep = pause,
    maxWaitMs = 60_000,
  }: { onBusy?: () => void; sleep?: (ms: number) => Promise<void>; maxWaitMs?: number } = {},
): AsyncGenerator<TurnEvent> {
  let waited = 0;
  for (;;) {
    try {
      // A busy answer comes before any event, so a retry never repeats one.
      yield* run();
      return;
    } catch (error) {
      const seconds = error instanceof ApiError && error.status === 429 ? error.retryAfter : null;
      if (seconds !== null && seconds > BUSY_RETRY_MAX_SECONDS) {
        throw new ApiError(questionLimitText(seconds), 429, seconds);
      }
      if (seconds === null || waited + seconds * 1000 > maxWaitMs) throw error;
      onBusy?.();
      await sleep(seconds * 1000);
      waited += seconds * 1000;
    }
  }
}

/**
 * Poll a thread whose turn is in flight (a reload mid-turn) until it ends,
 * backing off from `firstDelayMs` by half again each time up to `maxDelayMs`.
 * A failed poll is retried; the wait gives up after `maxWaitMs`.
 */
export async function waitForTurn(
  getThread: (threadId: string) => Promise<ThreadView>,
  threadId: string,
  {
    sleep = pause,
    firstDelayMs = 1500,
    maxDelayMs = 8000,
    maxWaitMs = 6 * 60_000,
    signal,
  }: WaitOptions = {},
): Promise<ThreadView> {
  let delay = firstDelayMs;
  let waited = 0;
  while (waited < maxWaitMs) {
    signal?.throwIfAborted();
    await sleep(delay);
    waited += delay;
    delay = Math.min(maxDelayMs, delay * 1.5);
    signal?.throwIfAborted();
    try {
      const view = await getThread(threadId);
      if (!view.turn_in_flight) return view;
    } catch {
      // A blip while the turn runs (a waking host, a dropped connection): keep waiting.
    }
    signal?.throwIfAborted();
  }
  throw new ApiError(TURN_WAIT_TIMEOUT, 504);
}
