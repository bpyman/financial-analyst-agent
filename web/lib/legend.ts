/**
 * A trend legend's state: which series are hidden, and which one the pointer
 * or keyboard is on. Hovering or focusing a series brings it forward and dims
 * the rest; clicking hides or shows it.
 */
export interface LegendState {
  hidden: string[];
  focus: string | null;
}

export const NO_LEGEND: LegendState = { hidden: [], focus: null };

/** Hides or shows `key`; the last series shown stays, so the chart is never empty. */
export function toggleSeries(state: LegendState, key: string, all: string[]): LegendState {
  if (state.hidden.includes(key)) return { ...state, hidden: state.hidden.filter((each) => each !== key) };
  const shown = all.filter((each) => !state.hidden.includes(each));
  if (shown.length <= 1) return state;
  return { ...state, hidden: [...state.hidden, key] };
}

export function emphasis(state: LegendState, key: string): "focus" | "dim" | "normal" | "hidden" {
  if (state.hidden.includes(key)) return "hidden";
  if (state.focus === null || state.hidden.includes(state.focus)) return "normal";
  return state.focus === key ? "focus" : "dim";
}
