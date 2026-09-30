/**
 * Which words of a changed paragraph are new, and which went away: a
 * longest-common-subsequence over words, so "may" becoming "could" stands out
 * in a paragraph that otherwise reads the same. Whitespace rides along with the
 * word before it, so the text reads exactly as filed.
 */
export interface DiffPiece {
  text: string;
  changed: boolean;
}

export interface WordDiff {
  before: DiffPiece[];
  after: DiffPiece[];
}

// Beyond this many word pairs the table is too big to build in a click; the
// paragraphs are then shown without highlighting.
const MAX_CELLS = 1_500_000;

function words(text: string): string[] {
  return text.match(/\S+\s*/g) ?? [];
}

function key(word: string): string {
  return word.trim();
}

function pieces(tokens: string[], kept: boolean[]): DiffPiece[] {
  const merged: DiffPiece[] = [];
  tokens.forEach((token, index) => {
    const changed = !kept[index];
    const last = merged[merged.length - 1];
    if (last && last.changed === changed) last.text += token;
    else merged.push({ text: token, changed });
  });
  // A mark ends at its last word; the space after it is ordinary text.
  return merged.flatMap((piece) => {
    const space = /\s+$/.exec(piece.text)?.[0];
    if (!piece.changed || !space) return [piece];
    return [
      { text: piece.text.slice(0, -space.length), changed: true },
      { text: space, changed: false },
    ];
  });
}

/** The two texts cut into kept and changed runs, or null when too long to compare. */
export function wordDiff(before: string, after: string): WordDiff | null {
  const left = words(before);
  const right = words(after);
  if (!left.length || !right.length) return null;
  if (left.length * right.length > MAX_CELLS) return null;
  const width = right.length + 1;
  // lengths[i * width + j]: common words of left[i:] and right[j:].
  const lengths = new Uint32Array((left.length + 1) * width);
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      lengths[i * width + j] =
        key(left[i]) === key(right[j])
          ? lengths[(i + 1) * width + j + 1] + 1
          : Math.max(lengths[(i + 1) * width + j], lengths[i * width + j + 1]);
    }
  }
  const keptLeft = new Array<boolean>(left.length).fill(false);
  const keptRight = new Array<boolean>(right.length).fill(false);
  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    if (key(left[i]) === key(right[j])) {
      keptLeft[i] = true;
      keptRight[j] = true;
      i += 1;
      j += 1;
    } else if (lengths[(i + 1) * width + j] >= lengths[i * width + j + 1]) {
      i += 1;
    } else {
      j += 1;
    }
  }
  const lead = (text: string) => /^\s*/.exec(text)?.[0] ?? "";
  const withLead = (text: string, runs: DiffPiece[]) =>
    lead(text) ? [{ text: lead(text), changed: false }, ...runs] : runs;
  return {
    before: withLead(before, pieces(left, keptLeft)),
    after: withLead(after, pieces(right, keptRight)),
  };
}
