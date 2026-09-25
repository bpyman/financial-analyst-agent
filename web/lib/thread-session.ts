// One thread per browser (ADR 0006): the id lives in local storage so a reload
// resumes it; Start over and a runtime switch replace it with a new one.

import { ApiError } from "./api";
import type { CreatedThread, RuntimeKind, ThreadView } from "./types";

export const THREAD_STORAGE_KEY = "financial-analyst-agent.thread-id";
export const EXPIRED_NOTICE = "Your previous thread has expired, so this is a fresh start.";

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

/**
 * The stored thread, if the server still has it. A thread that comes back
 * unknown or empty has expired (TTL or a restarted host): it is forgotten and
 * the analyst is told. An outage rethrows and keeps the id for a retry.
 */
export async function resumeThread(
  api: ThreadApi,
  store: KeyValueStore,
): Promise<ThreadOutcome<ThreadView | null>> {
  const threadId = store.getItem(THREAD_STORAGE_KEY);
  if (!threadId) return { view: null, notice: null };
  let view: ThreadView;
  try {
    view = await api.getThread(threadId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return forget(store);
    throw error;
  }
  if (view.runtime === null && view.turns.length === 0) return forget(store);
  return { view, notice: null };
}

function forget(store: KeyValueStore): ThreadOutcome<null> {
  store.removeItem(THREAD_STORAGE_KEY);
  return { view: null, notice: EXPIRED_NOTICE };
}

/**
 * Start a new thread bound to `runtime`, clearing `previousId` first. Start
 * over is this on the same runtime; switching runtime is this on the other.
 */
export async function startThread(
  api: ThreadApi,
  store: KeyValueStore,
  runtime: RuntimeKind,
  previousId?: string | null,
): Promise<ThreadOutcome<ThreadView>> {
  if (previousId) {
    try {
      await api.deleteThread(previousId);
    } catch {
      // Best effort: the old thread expires on its own.
    }
  }
  store.removeItem(THREAD_STORAGE_KEY);
  const created = await api.createThread(runtime);
  store.setItem(THREAD_STORAGE_KEY, created.thread_id);
  const view = await api.getThread(created.thread_id);
  return { view, notice: created.notice };
}
