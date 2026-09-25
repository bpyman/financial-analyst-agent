// The lifecycle of one streamed turn. Only one runs at a time per window.

import type { TurnEvent } from "./types";

export type TurnState =
  | { status: "idle" }
  | {
      status: "running";
      /** Empty when the window reattached to a turn it did not send (a reload mid-turn). */
      message: string;
      progress: { done: number; total: number } | null;
      /** Nothing has come back yet and the host is probably asleep. */
      waking: boolean;
    }
  | { status: "failed"; message: string; error: string };

export type TurnAction =
  | { type: "send"; message: string }
  | { type: "reattach" }
  | { type: "event"; event: TurnEvent }
  | { type: "wake" }
  | { type: "fail"; error: string }
  | { type: "reset" };

export const IDLE: TurnState = { status: "idle" };

/** How long a turn may show nothing before the window says the service is waking. */
export const WAKE_AFTER_MS = 3000;

export function turnReducer(state: TurnState, action: TurnAction): TurnState {
  switch (action.type) {
    case "send":
      if (state.status === "running") return state;
      return { status: "running", message: action.message, progress: null, waking: false };
    case "reattach":
      if (state.status === "running") return state;
      return { status: "running", message: "", progress: null, waking: false };
    case "wake":
      if (state.status !== "running" || state.progress !== null || state.waking) return state;
      return { ...state, waking: true };
    case "event": {
      if (state.status !== "running") return state;
      const { event } = action;
      if (event.event === "progress") return { ...state, progress: event.data, waking: false };
      if (event.event === "error") {
        return { status: "failed", message: state.message, error: event.data.message };
      }
      return IDLE;
    }
    case "fail":
      if (state.status !== "running") return state;
      return { status: "failed", message: state.message, error: action.error };
    case "reset":
      return IDLE;
  }
}

export function progressLabel(state: Extract<TurnState, { status: "running" }>): string {
  if (state.waking) return "Waking the analysis service…";
  if (state.progress === null) {
    return state.message ? "Sending your question…" : "Finishing your last question…";
  }
  const { done, total } = state.progress;
  if (total <= 0) return "Planning the analysis…";
  return `Fetched ${done} of ${total} ${total === 1 ? "cell" : "cells"}`;
}

export function turnCounterLabel(count: number, max: number): string {
  return `${count} of ${max} ${max === 1 ? "turn" : "turns"}`;
}
