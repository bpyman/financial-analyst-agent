import { describe, expect, it } from "vitest";
import { wordDiff } from "./word-diff";

const joined = (pieces: { text: string }[]) => pieces.map((piece) => piece.text).join("");
const changed = (pieces: { text: string; changed: boolean }[]) =>
  pieces.filter((piece) => piece.changed).map((piece) => piece.text.trim());

describe("wordDiff", () => {
  it("marks the words that changed and keeps the text as filed", () => {
    const before = "Demand may slow as rates rise.";
    const after = "Demand could slow sharply as rates rise.";
    const diff = wordDiff(before, after);

    expect(diff).not.toBeNull();
    expect(joined(diff!.before)).toBe(before);
    expect(joined(diff!.after)).toBe(after);
    expect(changed(diff!.before)).toEqual(["may"]);
    expect(changed(diff!.after)).toEqual(["could", "sharply"]);
  });

  it("gives up on pairs too long to compare in a click", () => {
    const long = "word ".repeat(2000);
    expect(wordDiff(long, long + "more")).toBeNull();
  });
});
