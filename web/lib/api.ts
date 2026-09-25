import { createSseParser } from "./sse";
import type { CreatedThread, Meta, RuntimeKind, ThreadView, TurnEvent } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function detail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // fall through
  }
  return response.status >= 500
    ? "The analysis service is unavailable. Please try again."
    : `Request failed (${response.status}).`;
}

async function json<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, { cache: "no-store", ...init });
  if (!response.ok) throw new ApiError(await detail(response), response.status);
  return (await response.json()) as T;
}

/** Storefront copy; `runtime` picks whose snapshot banner to report (the deployment default when omitted). */
export function getMeta(runtime?: RuntimeKind): Promise<Meta> {
  return json<Meta>(runtime ? `/api/meta?runtime=${runtime}` : "/api/meta");
}

/** Wake the hosted API while the visitor reads the landing page (ADR 0006). */
export function pingHealth(): void {
  fetch("/api/health", { cache: "no-store" }).catch(() => undefined);
}

/** Start a thread bound to `runtime` (the deployment default when omitted). */
export function createThread(runtime?: RuntimeKind): Promise<CreatedThread> {
  return json<CreatedThread>("/api/threads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(runtime ? { runtime } : {}),
  });
}

export function getThread(threadId: string): Promise<ThreadView> {
  return json<ThreadView>(`/api/threads/${encodeURIComponent(threadId)}`);
}

export async function deleteThread(threadId: string): Promise<void> {
  const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 404) {
    throw new ApiError(await detail(response), response.status);
  }
}

/** POST a turn on the thread's own runtime and yield server-sent events until `thread` or `error`. */
export async function* runTurn(
  threadId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<TurnEvent> {
  const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(await detail(response), response.status);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parse = createSseParser();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const message of parse(value)) {
        const event = { event: message.event, data: JSON.parse(message.data) } as TurnEvent;
        yield event;
        if (event.event === "thread" || event.event === "error") return;
      }
    }
  } finally {
    reader.releaseLock();
  }
  throw new ApiError("The connection closed before the analysis finished.", 502);
}
