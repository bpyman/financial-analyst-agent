import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import {
  EXPIRED_NOTICE,
  LOCKED_LIVE_NOTICE,
  THREAD_STORAGE_KEY,
  ThreadMovedError,
  askOnThread,
  isCurrentThread,
  memoryStore,
  resumeThread,
  startOverIfLocked,
  startThread,
  threadLimitText,
  waitForTurn,
  waitPhrase,
  type ThreadApi,
  whenFree,
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

  it.each([400, 405, 414, 431])("forgets an unusable stored id after HTTP %s", async (status) => {
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "invalid" });
    const api = fakeApi({ invalid: new ApiError("Invalid thread id.", status) });
    expect(await resumeThread(api, store)).toEqual({ view: null, notice: EXPIRED_NOTICE });
    expect(store.getItem(THREAD_STORAGE_KEY)).toBeNull();
    expect(api.createThread).not.toHaveBeenCalled();
  });

  it("forgets a stored id that cannot name a thread, without asking the server", async () => {
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "../threads/x" });
    const api = fakeApi();
    expect(await resumeThread(api, store)).toEqual({ view: null, notice: EXPIRED_NOTICE });
    expect(store.getItem(THREAD_STORAGE_KEY)).toBeNull();
    expect(api.getThread).not.toHaveBeenCalled();
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

  it("makes the new thread, then clears the previous one (Start over)", async () => {
    const api = fakeApi({ "t-1": view({ thread_id: "t-1", turn_count: 4 }) });
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });
    const started = await startThread(api, store, "recorded", "t-1");
    expect(api.deleteThread).toHaveBeenCalledWith("t-1");
    expect(api.createThread.mock.invocationCallOrder[0]).toBeLessThan(
      api.deleteThread.mock.invocationCallOrder[0],
    );
    expect(started.view.thread_id).not.toBe("t-1");
    expect(started.view.turn_count).toBe(0);
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe(started.view.thread_id);
  });

  it("keeps the current thread when a new one cannot start, and says how long to wait", async () => {
    const api = fakeApi({ "t-1": view({ thread_id: "t-1", turn_count: 4 }) });
    api.createThread.mockRejectedValueOnce(new ApiError("You've asked a lot of questions.", 429, 600));
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-1" });

    const refused = await startThread(api, store, "recorded", "t-1").catch((error: unknown) => error);

    expect(refused).toMatchObject({ status: 429, message: threadLimitText(600) });
    expect(threadLimitText(600)).toContain("in about 10 minutes");
    expect(api.deleteThread).not.toHaveBeenCalled();
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe("t-1");
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

  it("follows another tab's Start over instead of starting a third thread", async () => {
    const api = fakeApi();
    // The other tab replaced "t-1" with "t-2" while this one's question was on its way.
    const store = memoryStore({ [THREAD_STORAGE_KEY]: "t-2" });
    const runTurn = fakeTurns({ "t-1": new ApiError("Unknown thread.", 404) });

    const moved = await collect(askOnThread(api, store, runTurn, "t-1", "hi", "recorded", vi.fn())).catch(
      (error: unknown) => error,
    );

    expect(moved).toBeInstanceOf(ThreadMovedError);
    expect(moved).toMatchObject({ threadId: "t-2" });
    expect(api.createThread).not.toHaveBeenCalled();
    expect(store.getItem(THREAD_STORAGE_KEY)).toBe("t-2");
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

describe("whenFree", () => {
  const done: TurnEvent = { event: "thread", data: {} as ThreadView };
  const busy = () => new ApiError("busy", 429, 5);

  async function collect(events: AsyncIterable<TurnEvent>): Promise<TurnEvent[]> {
    const seen: TurnEvent[] = [];
    for await (const event of events) seen.push(event);
    return seen;
  }

  it("waits the seconds a busy server asks, then runs the turn", async () => {
    let tries = 0;
    const slept: number[] = [];
    const onBusy = vi.fn();
    const events = await collect(
      whenFree(
        async function* () {
          tries += 1;
          if (tries < 3) throw busy();
          yield done;
        },
        { onBusy, sleep: async (ms) => void slept.push(ms) },
      ),
    );
    expect(events).toEqual([done]);
    expect(slept).toEqual([5000, 5000]);
    expect(onBusy).toHaveBeenCalledTimes(2);
  });

  it("gives up after a minute, and never waits out a visitor's hourly limit", async () => {
    const always = async function* (): AsyncGenerator<TurnEvent> {
      throw busy();
    };
    await expect(collect(whenFree(always, { sleep: async () => undefined }))).rejects.toThrow("busy");

    const limited = async function* (): AsyncGenerator<TurnEvent> {
      throw new ApiError("limit", 429, 900);
    };
    const sleep = vi.fn(async () => undefined);
    await expect(collect(whenFree(limited, { sleep }))).rejects.toThrow(
      "You've asked a lot of questions in the last hour. You can ask again in about 15 minutes.",
    );
    expect(sleep).not.toHaveBeenCalled();
  });
});

describe("waitPhrase", () => {
  it("names the wait in words", () => {
    expect(waitPhrase(null)).toBe("in a little while");
    expect(waitPhrase(20)).toBe("in 20 seconds");
    expect(waitPhrase(70)).toBe("in about a minute");
    expect(waitPhrase(3600)).toBe("in about 60 minutes");
    expect(waitPhrase(7200)).toBe("in about 2 hours");
  });
});
