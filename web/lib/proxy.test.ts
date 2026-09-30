import { describe, expect, it } from "vitest";
import {
  CLIENT_IP_HEADER,
  MAX_BODY_BYTES,
  PROXY_TOKEN_HEADER,
  clientAddress,
  clientResponseHeaders,
  passesThrough,
  refusal,
  upstreamRequestHeaders,
} from "./proxy";

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

  it("passes on how long a busy API asks the caller to wait", () => {
    const upstream = new Headers({ "content-type": "application/json", "retry-after": "5" });
    expect(clientResponseHeaders(upstream).get("retry-after")).toBe("5");
  });
});

describe("clientAddress", () => {
  it("prefers the platform's x-real-ip, then the first x-forwarded-for hop", () => {
    expect(clientAddress(browserRequest({ headers: { "x-real-ip": "203.0.113.9" } }))).toBe("203.0.113.9");
    expect(
      clientAddress(browserRequest({ headers: { "x-forwarded-for": "198.51.100.4, 10.0.0.1" } })),
    ).toBe("198.51.100.4");
    expect(clientAddress(browserRequest())).toBeNull();
  });

  it("is forwarded to the API as its own header", () => {
    const headers = upstreamRequestHeaders(browserRequest({ headers: { "x-real-ip": "203.0.113.9" } }), "t");
    expect(headers.get(CLIENT_IP_HEADER)).toBe("203.0.113.9");
  });
});

describe("refusal", () => {
  const post = (headers: Record<string, string>) =>
    browserRequest({ method: "POST", body: "{}", headers: { "content-type": "application/json", ...headers } });

  it("refuses dot segments", () => {
    expect(refusal(browserRequest(), ["threads", ".."])?.status).toBe(404);
    expect(refusal(browserRequest(), ["threads", "."])?.status).toBe(404);
  });

  it("refuses changes sent from another site", () => {
    expect(refusal(post({ "sec-fetch-site": "cross-site" }), ["threads"])?.status).toBe(403);
    expect(refusal(post({ "sec-fetch-site": "same-site" }), ["threads"])?.status).toBe(403);
    expect(refusal(post({ "sec-fetch-site": "same-origin" }), ["threads"])).toBeNull();
    expect(refusal(post({}), ["threads"])).toBeNull();
  });

  it("lets reads through from anywhere", () => {
    const read = browserRequest({ headers: { "sec-fetch-site": "cross-site" } });
    expect(refusal(read, ["health"])).toBeNull();
  });

  it("refuses a declared body over the limit", () => {
    expect(refusal(post({ "content-length": String(MAX_BODY_BYTES + 1) }), ["threads"])?.status).toBe(413);
  });
});

describe("passesThrough", () => {
  it("passes JSON, event streams and empty answers, and nothing else", () => {
    const answer = (status: number, type?: string) =>
      new Response(status === 204 ? null : "x", { status, headers: type ? { "content-type": type } : {} });
    expect(passesThrough(answer(200, "application/json; charset=utf-8"))).toBe(true);
    expect(passesThrough(answer(200, "text/event-stream"))).toBe(true);
    expect(passesThrough(answer(204))).toBe(true);
    expect(passesThrough(answer(500, "text/html"))).toBe(false);
    expect(passesThrough(answer(502, "text/plain"))).toBe(false);
  });
});
