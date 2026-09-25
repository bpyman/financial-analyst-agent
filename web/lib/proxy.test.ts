import { describe, expect, it } from "vitest";
import { PROXY_TOKEN_HEADER, clientResponseHeaders, upstreamRequestHeaders } from "./proxy";

function browserRequest(init: RequestInit = {}): Request {
  return new Request("http://localhost:3000/api/threads", init);
}

describe("upstreamRequestHeaders", () => {
  it("adds the shared secret when API_PROXY_TOKEN is configured", () => {
    const headers = upstreamRequestHeaders(browserRequest(), "s3cret");
    expect(headers.get(PROXY_TOKEN_HEADER)).toBe("s3cret");
  });

  it.each([undefined, ""])("sends no secret header when the token is %j", (token) => {
    const headers = upstreamRequestHeaders(browserRequest(), token);
    expect(headers.has(PROXY_TOKEN_HEADER)).toBe(false);
  });

  it("never forwards a secret header the browser made up", () => {
    const forged = browserRequest({ headers: { [PROXY_TOKEN_HEADER]: "guess" } });
    expect(upstreamRequestHeaders(forged, undefined).has(PROXY_TOKEN_HEADER)).toBe(false);
    expect(upstreamRequestHeaders(forged, "s3cret").get(PROXY_TOKEN_HEADER)).toBe("s3cret");
  });

  it("passes accept, and content-type only for requests with a body", () => {
    const get = upstreamRequestHeaders(browserRequest({ headers: { accept: "text/event-stream" } }), "t");
    expect(get.get("accept")).toBe("text/event-stream");
    expect(get.has("content-type")).toBe(false);
    const post = upstreamRequestHeaders(
      browserRequest({ method: "POST", body: "{}", headers: { "content-type": "application/json" } }),
      "t",
    );
    expect(post.get("accept")).toBe("application/json");
    expect(post.get("content-type")).toBe("application/json");
    const bare = upstreamRequestHeaders(browserRequest({ method: "DELETE" }), "t");
    expect(bare.get("content-type")).toBe("application/json");
  });
});

describe("clientResponseHeaders", () => {
  it("keeps only the stream-safe headers, so an echoed secret never reaches the browser", () => {
    const upstream = new Headers({
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
      [PROXY_TOKEN_HEADER]: "s3cret",
      "set-cookie": "a=b",
    });
    expect([...clientResponseHeaders(upstream).entries()]).toEqual([
      ["cache-control", "no-cache, no-transform"],
      ["content-type", "text/event-stream"],
      ["x-accel-buffering", "no"],
    ]);
  });
});
