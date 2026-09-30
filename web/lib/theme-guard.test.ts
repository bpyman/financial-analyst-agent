import { describe, expect, it } from "vitest";
import { THEME_GUARD_SCRIPT } from "./theme-guard";

function run(stored: string | null): string | null {
  const values = new Map<string, string>(stored === null ? [] : [["theme", stored]]);
  const localStorage = {
    getItem: (key: string) => values.get(key) ?? null,
    removeItem: (key: string) => void values.delete(key),
  };
  new Function("localStorage", THEME_GUARD_SCRIPT)(localStorage);
  return values.get("theme") ?? null;
}

describe("THEME_GUARD_SCRIPT", () => {
  it("keeps the themes next-themes stores", () => {
    for (const theme of ["light", "dark", "system"]) expect(run(theme)).toBe(theme);
    expect(run(null)).toBeNull();
  });

  it("drops a corrupt value before it can reach the html class", () => {
    expect(run('{"bad":')).toBeNull();
    expect(run("dark evil")).toBeNull();
  });
});
