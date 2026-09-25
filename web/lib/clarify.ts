import type { Turn } from "./types";

export interface ClarifyChoice {
  /** The catalog slug a button sends as the next analyst message (ADR 0006). */
  slug: string;
  /** The server's label for it. */
  label: string;
  /** The next message answered with this candidate. */
  chosen: boolean;
}

const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();

/** A clarification's candidates, and which one the following turn chose. */
export function clarifyChoices(turn: Turn, next?: Pick<Turn, "message">): ClarifyChoice[] {
  const labels = turn.presentation.candidates;
  return turn.candidate_slugs.map((slug, index) => {
    const label = labels[index] || slug;
    const chosen = next !== undefined && (same(next.message, slug) || same(next.message, label));
    return { slug, label, chosen };
  });
}

/** An analyst message as the thread shows it: a clarify answer reads as its label. */
export function shownMessage(turn: Pick<Turn, "message">, previous?: Turn): string {
  if (!previous) return turn.message;
  const choice = clarifyChoices(previous, turn).find((candidate) => candidate.chosen);
  return choice ? choice.label : turn.message;
}
