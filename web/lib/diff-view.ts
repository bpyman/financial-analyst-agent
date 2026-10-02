import type { DisplayDisclosure } from "./types";
import type { UnifiedPiece } from "./word-diff";

/**
 * How the 10-Q changes are laid out: what moved a number first, in the filing's
 * order, then other edits larger before smaller, and edits that only reword
 * folded away. The text itself is the filing's, untouched.
 */

const FIGURE = /\$?\d[\d,]*(?:\.\d+)?%?/g;

function figures(text: string): string[] {
  return (text.match(FIGURE) ?? []).sort();
}

/** Whether a changed paragraph's figures differ, not only its words. */
export function changesFigures(item: DisplayDisclosure): boolean {
  const before = figures(item.before_text);
  const after = figures(item.after_text);
  return before.length !== after.length || before.some((figure, index) => figure !== after[index]);
}

/** A rewording: the paragraph changed, its figures did not. */
export function isWordingOnly(item: DisplayDisclosure): boolean {
  return item.change_kind === "changed" && !changesFigures(item);
}

/** How much changed, in words gone or come. */
function size(item: DisplayDisclosure): number {
  const words = (text: string) => new Set(text.split(/\s+/).filter(Boolean));
  const before = words(item.before_text);
  const after = words(item.after_text);
  let changed = 0;
  for (const word of before) if (!after.has(word)) changed += 1;
  for (const word of after) if (!before.has(word)) changed += 1;
  return changed;
}

/**
 * Figures that moved within a paragraph first, in the filing's order (it leads
 * with its headline figures); then additions, removals and other edits, larger
 * before smaller; then rewordings. A paragraph added or removed whole has
 * figures on one side only, but says less than "20% to 29%".
 */
export function orderChanges(items: DisplayDisclosure[]): DisplayDisclosure[] {
  const rank = (item: DisplayDisclosure) =>
    isWordingOnly(item) ? 2 : item.change_kind === "changed" && changesFigures(item) ? 0 : 1;
  return items
    .map((item, index) => ({ item, index, rank: rank(item), size: size(item) }))
    .sort((a, b) => a.rank - b.rank || (a.rank === 1 ? b.size - a.size : 0) || a.index - b.index)
    .map(({ item }) => item);
}

// A sentence ends at . ! or ? followed by space and a capital or an opening mark.
const SENTENCE_END = /([.!?]["”’)]?\s+)(?=[A-Z(“"'])/g;

/**
 * The sentences of a merged paragraph that hold a change, each as its runs;
 * `omitted` says sentences that read the same were left out.
 */
export function changedSentences(pieces: UnifiedPiece[]): { sentences: UnifiedPiece[][]; omitted: boolean } {
  const sentences: UnifiedPiece[][] = [[]];
  for (const piece of pieces) {
    if (piece.kind !== "same") {
      sentences[sentences.length - 1].push(piece);
      continue;
    }
    // Only kept text splits: a sentence break inside an edit stays with the edit.
    const parts = piece.text.split(SENTENCE_END);
    for (let index = 0; index < parts.length; index += 2) {
      const text = parts[index] + (parts[index + 1] ?? "");
      if (text) sentences[sentences.length - 1].push({ text, kind: "same" });
      if (parts[index + 1] !== undefined) sentences.push([]);
    }
  }
  const kept = sentences.filter((sentence) => sentence.some((piece) => piece.kind !== "same"));
  return { sentences: kept, omitted: kept.length < sentences.filter((sentence) => sentence.length).length };
}
