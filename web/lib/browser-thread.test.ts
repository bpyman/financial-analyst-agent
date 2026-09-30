import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import {
  EXPIRED_NOTICE,
  LOCKED_LIVE_NOTICE,
  THREAD_STORAGE_KEY,
  askOnThread,
  isCurrentThread,
  memoryStore,
  resumeThread,
  startOverIfLocked,
  startThread,
  waitForTurn,
  type ThreadApi,
} from "./browser-thread";
import type { CreatedThread, RuntimeKind, ThreadView, TurnEvent } from "./types";

function view(overrides: Partial<ThreadView> = {}): ThreadView {
  return {
    thread_id: "t-1",
    runtime: "recorded",
    turns: [],
    spec_chips: [],
    pending_clarification: false,
    turn_count: 0,
    max_turns: 25,
    turn_in_flight: false,
    ...overrides,
  };
}

function fakeApi(threads: Record<string, ThreadView | ApiError> = {}) {
  let minted = 0;
  const api = {
    createThread: vi.fn(async (runtime?: RuntimeKind): Promise<CreatedThread> => {
      minted += 1;
      const id = `new-${minted}`;
      const bound = runtime ?? "recorded";
      threads[id] = view({ thread_id: id, runtime: bound });
      return { thread_id: id, runtime: bound, notice: null };
    }),
    getThread: vi.fn(async (id: string): Promise<ThreadView> => {
      const found = threads[id];
      if (found === undefined) throw new ApiError("Unknown thread.", 404);
      if (found instanceof ApiError) throw found;
      return found;
    }),
    deleteThread: vi.fn(async (id: string) => {
      delete threads[id];
    }),
  } satisfies ThreadApi;
  return api;
}

describe("resumeThread", () => {
  it("has nothing to resume on a first visit", async () => {
    const api = fakeApi();
    expect(await resumeThread(api, memoryStore())).toEqual({ view: null, notice: null });
    expect(api.getThread).not.toHaveBeenCalled();
  });

  it("returns the stored thread after a reload", async () => {
    const saved = view({ thread_id: "t-1", turn_count: 3 });
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });
    expect(await resumeThread(fakeApi({ "t-1": saved }), store)).toEqual({
      view: saved,
      notice: null,
    });
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe("t-1");
  });

  it("says so quietly and forgets a thread that came back empty", async () => {
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });
    const expired = view({ runtime: null });
    expect(await resumeThread(fakeApi({ "t-1": expired }), store)).toEqual({
      view: null,
      notice: EXPIRED_NOTICE,
    });
    expect(store.getItem(THREAD_STORAGE_KEY)).toBeNull();
  });

  it("treats an unknown thread id as expired", async () => {
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "gone" });
    expect(await resumeThread(fakeApi(), store)).toEqual({ view: null, notice: EXPIRED_NOTICE });
    expect(store.getItem(THREAD_STORAGE_KEY)).toBeNull();
  });

  it.each([400, 414, 431])("forgets an unusable stored id after HTTP %s", async (status) => {
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "invalid" });
    const api = fakeApi({ invalid: new ApiError("Invalid thread id.", status) });
    expect(await resumeThread(api, store)).toEqual({ view: null, notice: EXPIRED_NOTICE });
    expect(store.getItem(THREAD_STORAGE_KEY)).toBeNull();
    expect(api.createThread).not.toHaveBeenCalled();
  });

  it.each([new TypeError("Failed to fetch"), new ApiError("Unavailable", 503)])(
    "resumes the same thread after a transient failure: %s",
    async (error) => {
      const saved = view();
      const api = fakeApi({ "t-1": saved });
      api.getThread.mockRejectedValueOnce(error);
      const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });
      await expect(resumeThread(api, store)).rejects.toBe(error);
      expect(store.getItem(THREAD_STORAGE_KEY)).toBe("t-1");
      expect(await resumeThread(api, store)).toEqual({ view: saved, notice: null });
      expect(api.createThread).not.toHaveBeenCalled();
    },
  );

  it("keeps the stored id when the service is down, so a retry can resume it", async () => {
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });
    const outage = new ApiError("The analysis service is unreachable.", 502);
    await expect(resumeThread(fakeApi({ "t-1": outage }), store)).rejects.toBe(outage);
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe("t-1");
  });

  it("drops a restoration that lands after the analyst started another thread", async () => {
    const api = fakeApi({ "t-1": view({ thread_id: "t-1", turn_count: 3 }) });
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });
    let release = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    api.getThread.mockImplementationOnce(async (id) => {
      await held;
      return view({ thread_id: id, turn_count: 3 });
    });

    const resuming = resumeThread(api, store);
    const started = await startThread(api, store, "recorded", "t-1");
    release();

    expect(await resuming).toBeNull();
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe(started.view.thread_id);
  });

  it("does not forget the new thread when the one it replaced comes back expired", async () => {
    const api = fakeApi();
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "gone" });
    let release = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    api.getThread.mockImplementationOnce(async () => {
      await held;
      throw new ApiError("Unknown thread.", 404);
    });

    const resuming = resumeThread(api, store);
    store.setItem(THREAD_STORAGE_KEY, "new-1");
    release();

    expect(await resuming).toBeNull();
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe("new-1");
  });
});

describe("isCurrentThread", () => {
  it("is true only for the thread this browser holds", () => {
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-2" });
    expect(isCurrentThread(store, "t-2")).toBe(true);
    expect(isCurrentThread(store, "t-1")).toBe(false);
    expect(isCurrentThread(memoryStore(), "t-1")).toBe(false);
  });
});

describe("startThread", () => {
  it("creates a thread on the requested runtime and remembers it", async () => {
    const api = fakeApi();
    const store = memoryStore();
    const started = await startThread(api, store, "live");
    expect(api.createThread).toHaveBeenCalledWith("live");
    expect(started.view.runtime).toBe("live");
    expect(started.view.max_turns).toBe(25);
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe(started.view.thread_id);
  });

  it("clears the previous thread first (Start over)", async () => {
    const api = fakeApi({ "t-1": view({ thread_id: "t-1", turn_count: 4 }) });
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });
    const started = await startThread(api, store, "recorded", "t-1");
    expect(api.deleteThread).toHaveBeenCalledWith("t-1");
    expect(started.view.thread_id).not.toBe("t-1");
    expect(started.view.turn_count).toBe(0);
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe(started.view.thread_id);
  });

  it("still starts fresh when the old thread cannot be deleted", async () => {
    const api = fakeApi();
    api.deleteThread.mockRejectedValueOnce(new ApiError("A turn is already running.", 409));
    const started = await startThread(api, memoryStore(), "recorded", "t-1");
    expect(started.view.thread_id).toBe("new-1");
  });

  it("passes on the server's notice when it served another runtime", async () => {
    const api = fakeApi();
    api.createThread.mockImplementationOnce(async () => ({
      thread_id: "new-9",
      runtime: "recorded",
      notice: "Live runtime is off on the public demo",
    }));
    api.getThread.mockImplementationOnce(async () => view({ thread_id: "new-9" }));
    const started = await startThread(api, memoryStore(), "live");
    expect(started.notice).toBe("Live runtime is off on the public demo");
    expect(started.view.runtime).toBe("recorded");
  });
});

describe("startThread without a chosen runtime", () => {
  it("leaves the runtime to the deployment default", async () => {
    const api = fakeApi();
    await startThread(api, memoryStore(), undefined);
    expect(api.createThread).toHaveBeenCalledWith(undefined);
  });
});

describe("startOverIfLocked", () => {
  it("keeps a thread the deployment can run", async () => {
    const api = fakeApi();
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });
    expect(await startOverIfLocked(api, store, view({ runtime: "live" }), false)).toBeNull();
    expect(await startOverIfLocked(api, store, view({ runtime: "recorded" }), true)).toBeNull();
    expect(await startOverIfLocked(api, store, null, true)).toBeNull();
    expect(api.createThread).not.toHaveBeenCalled();
  });

  it("starts over on the recorded runtime when a live thread meets a locked deployment", async () => {
    const live = view({ thread_id: "t-live", runtime: "live", turn_count: 2 });
    const api = fakeApi({ "t-live": live });
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-live" });

    const started = await startOverIfLocked(api, store, live, true);

    expect(api.deleteThread).toHaveBeenCalledWith("t-live");
    expect(api.createThread).toHaveBeenCalledWith("recorded");
    expect(started).toEqual({ view: expect.objectContaining({ runtime: "recorded" }), notice: LOCKED_LIVE_NOTICE });
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe(started?.view.thread_id);
  });
});

describe("askOnThread", () => {
  const answered = (threadId: string): TurnEvent[] => [
    { event: "progress", data: { done: 0, total: 0 } },
    { event: "thread", data: view({ thread_id: threadId, turn_count: 1 }) },
  ];

  /** The turn endpoint: `refusals` maps a thread id to the error its POST gets. */
  function fakeTurns(refusals: Record<string, ApiError> = {}) {
    return vi.fn(async function* (threadId: string): AsyncGenerator<TurnEvent> {
      const refused = refusals[threadId];
      if (refused) throw refused;
      yield* answered(threadId);
    });
  }

  async function collect(events: AsyncIterable<TurnEvent>): Promise<TurnEvent[]> {
    const seen: TurnEvent[] = [];
    for await (const event of events) seen.push(event);
    return seen;
  }

  it("asks on the thread the server still has", async () => {
    const api = fakeApi();
    const runTurn = fakeTurns();
    const onFresh = vi.fn();

    const events = await collect(
      askOnThread(api, memoryStore(), runTurn, "t-1", "hi", "recorded", onFresh),
    );

    expect(events).toEqual(answered("t-1"));
    expect(api.createThread).not.toHaveBeenCalled();
    expect(onFresh).not.toHaveBeenCalled();
  });

  it("asks again on a fresh thread when the server lost the stored one", async () => {
    const api = fakeApi();
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "gone" });
    const runTurn = fakeTurns({ gone: new ApiError("Unknown thread.", 404) });
    const onFresh = vi.fn();

    const events = await collect(askOnThread(api, store, runTurn, "gone", "hi", "live", onFresh));

    expect(api.createThread).toHaveBeenCalledWith("live");
    expect(runTurn.mock.calls).toEqual([
      ["gone", "hi"],
      ["new-1", "hi"],
    ]);
    expect(events).toEqual(answered("new-1"));
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe("new-1");
    expect(onFresh).toHaveBeenCalledWith({
      view: expect.objectContaining({ thread_id: "new-1" }),
      notice: EXPIRED_NOTICE,
    });
  });

  it("passes other refusals on, such as a busy service", async () => {
    const api = fakeApi();
    const busy = new ApiError("The analysis service is busy. Please try again in a moment.", 429);
    const runTurn = fakeTurns({ "t-1": busy });

    await expect(
      collect(askOnThread(api, memoryStore(), runTurn, "t-1", "hi", "recorded", vi.fn())),
    ).rejects.toBe(busy);
    expect(api.createThread).not.toHaveBeenCalled();
  });
});

describe("waitForTurn", () => {
  it("polls with growing, capped delays until the turn in flight ends", async () => {
    const running = view({ turn_in_flight: true });
    const done = view({ turn_in_flight: false, turn_count: 1 });
    const getThread = vi
      .fn<(id: string) => Promise<ThreadView>>()
      .mockResolvedValueOnce(running)
      .mockRejectedValueOnce(new ApiError("The analysis service is unavailable.", 502))
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(done);
    const slept: number[] = [];
    const sleep = async (ms: number) => void slept.push(ms);

    const finished = await waitForTurn(getThread, "t-1", { sleep, firstDelayMs: 1500, maxDelayMs: 3000 });

    expect(finished).toBe(done);
    expect(getThread).toHaveBeenCalledWith("t-1");
    expect(slept).toEqual([1500, 2250, 3000, 3000, 3000]);
  });

  it("gives up after its time budget", async () => {
    const getThread = vi.fn(async () => view({ turn_in_flight: true }));
    const sleep = async () => undefined;
    await expect(
      waitForTurn(getThread, "t-1", { sleep, firstDelayMs: 1000, maxDelayMs: 1000, maxWaitMs: 3000 }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(getThread).toHaveBeenCalledTimes(3);
  });

  it("stops when cancelled", async () => {
    const controller = new AbortController();
    const getThread = vi.fn(async () => {
      controller.abort();
      return view({ turn_in_flight: true });
    });
    await expect(
      waitForTurn(getThread, "t-1", { sleep: async () => undefined, signal: controller.signal }),
    ).rejects.toThrow();
    expect(getThread).toHaveBeenCalledTimes(1);
  });
});

describe("memoryStore", () => {
  it("round-trips values", () => {
    const store = memoryStore();
    store.setItem("k", "v");
    expect(store.getItem("k")).toBe("v");
    store.removeItem("k");
    expect(store.getItem("k")).toBeNull();
  });
});
