import { describe, expect, it } from "vitest";
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
