import { describe, expect, it } from "vitest";
import { axisTick, parseLink } from "./format";
import { createSseParser } from "./sse";

describe("createSseParser", () => {
  it("parses messages split across arbitrary chunk boundaries", () => {
    const parse = createSseParser();
    const wire =
      'event: progress\ndata: {"done":1,"total":4}\n\n' +
      'event: thread\r\ndata: {"thread_id":"a",\r\ndata: "turns":[]}\r\n\r\n';
    const seen = [];
    for (let i = 0; i < wire.length; i += 7) seen.push(...parse(wire.slice(i, i + 7)));
    expect(seen).toEqual([
      { event: "progress", data: '{"done":1,"total":4}' },
      { event: "thread", data: '{"thread_id":"a",\n"turns":[]}' },
    ]);
  });

  it("ignores comments and blocks without data", () => {
    const parse = createSseParser();
    expect(parse(": keep-alive\n\nevent: noop\n\n")).toEqual([]);
  });
});

describe("axisTick", () => {
  it("compacts dollar ticks", () => {
    expect(axisTick(82_886_000_000, "usd")).toBe("$82.9B");
    expect(axisTick(1_500_000_000_000, "usd")).toBe("$1.5T");
    expect(axisTick(-300_000_000, "usd")).toBe("-$300M");
    expect(axisTick(0.253, "percent")).toBe("25%");
    expect(axisTick(12.34, "multiple")).toBe("12.3x");
  });
});

describe("parseLink", () => {
  it("accepts http(s) markdown links only", () => {
    expect(parseLink("[sec.gov](https://www.sec.gov/x.htm)")).toEqual({
      text: "sec.gov",
      href: "https://www.sec.gov/x.htm",
    });
    expect(parseLink("[x](javascript:alert(1))")).toBeNull();
    expect(parseLink("plain text")).toBeNull();
  });
});
