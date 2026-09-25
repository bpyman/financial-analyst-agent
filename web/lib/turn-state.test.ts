import { describe, expect, it } from "vitest";
import { IDLE, progressLabel, turnCounterLabel, turnReducer, type TurnState } from "./turn-state";

const run = (message = "What was Microsoft's latest quarterly pretax income?") =>
  turnReducer(IDLE, { type: "send", message });

describe("turnReducer", () => {
  it("runs one turn at a time", () => {
    const running = run();
    expect(running).toMatchObject({ status: "running", progress: null, waking: false });
    expect(turnReducer(running, { type: "send", message: "again" })).toBe(running);
  });

  it("says the service is waking only while nothing has come back", () => {
    const waking = turnReducer(run(), { type: "wake" });
    expect(waking).toMatchObject({ waking: true });
    const answered = turnReducer(waking, {
      type: "event",
      event: { event: "progress", data: { done: 0, total: 0 } },
    });
    expect(answered).toMatchObject({ waking: false, progress: { done: 0, total: 0 } });
    expect(turnReducer(answered, { type: "wake" })).toBe(answered);
    expect(turnReducer(IDLE, { type: "wake" })).toBe(IDLE);
  });

  it("returns to idle when the thread arrives", () => {
    const thread = {
      event: "thread" as const,
      data: {
        thread_id: "t",
        runtime: "recorded" as const,
        turns: [],
        spec_chips: [],
        pending_clarification: false,
        turn_count: 1,
        max_turns: 25,
        turn_in_flight: false,
      },
    };
    expect(turnReducer(run(), { type: "event", event: thread })).toEqual(IDLE);
  });

  it("keeps the question and the public error message when a turn fails", () => {
    const failed = turnReducer(run("q"), {
      type: "event",
      event: { event: "error", data: { message: "Session turn limit reached." } },
    });
    expect(failed).toEqual({ status: "failed", message: "q", error: "Session turn limit reached." });
    expect(turnReducer(run("q"), { type: "fail", error: "offline" })).toEqual({
      status: "failed",
      message: "q",
      error: "offline",
    });
    expect(turnReducer(failed, { type: "send", message: "q" })).toMatchObject({
      status: "running",
    });
    expect(turnReducer(failed, { type: "reset" })).toEqual(IDLE);
  });
});

describe("a turn already in flight after a reload", () => {
  it("runs without a message until the thread arrives", () => {
    const reattached = turnReducer(IDLE, { type: "reattach" });
    expect(reattached).toEqual({ status: "running", message: "", progress: null, waking: false });
    expect(progressLabel(reattached as Extract<TurnState, { status: "running" }>)).toBe(
      "Finishing your last question…",
    );
    expect(turnReducer(run(), { type: "reattach" })).toMatchObject({ message: expect.any(String) });
  });
});

describe("progressLabel", () => {
  const running = (patch: Partial<Extract<TurnState, { status: "running" }>>) => ({
    ...(run() as Extract<TurnState, { status: "running" }>),
    ...patch,
  });

  it("describes each phase of a turn", () => {
    expect(progressLabel(running({}))).toBe("Sending your question…");
    expect(progressLabel(running({ waking: true }))).toBe("Waking the analysis service…");
    expect(progressLabel(running({ progress: { done: 0, total: 0 } }))).toBe(
      "Planning the analysis…",
    );
    expect(progressLabel(running({ progress: { done: 1, total: 1 } }))).toBe(
      "Fetched 1 of 1 cell",
    );
    expect(progressLabel(running({ progress: { done: 3, total: 10 } }))).toBe(
      "Fetched 3 of 10 cells",
    );
  });
});

describe("turnCounterLabel", () => {
  it("counts turns against the thread's limit", () => {
    expect(turnCounterLabel(3, 25)).toBe("3 of 25 turns");
    expect(turnCounterLabel(1, 1)).toBe("1 of 1 turn");
  });
});
