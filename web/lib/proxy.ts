// Header rules for the same-origin proxy (app/api/[...path]/route.ts, ADR 0006).
// Server-side only: the token comes from the route's environment and is never
// sent back to the browser.

/** The shared-secret header the Python API checks when API_PROXY_TOKEN is set. */
export const PROXY_TOKEN_HEADER = "x-proxy-token";

/** Response headers the browser needs; everything else from upstream is dropped. */
const FORWARD_RESPONSE_HEADERS = ["content-type", "cache-control", "x-accel-buffering"];

/**
 * Headers for the upstream API call. Built from an allowlist, so nothing the
 * browser sent (a forged proxy token included) reaches the API; the proxy token
 * is added only when one is configured.
 */
export function upstreamRequestHeaders(request: Request, token: string | undefined): Headers {
  const headers = new Headers({ accept: request.headers.get("accept") ?? "application/json" });
  if (request.method !== "GET" && request.method !== "HEAD") {
    headers.set("content-type", request.headers.get("content-type") ?? "application/json");
  }
  if (token) headers.set(PROXY_TOKEN_HEADER, token);
  return headers;
}

/** Headers for the browser's response: only the allowlisted, stream-safe ones. */
export function clientResponseHeaders(upstream: Headers): Headers {
  const headers = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.get(name);
    if (value) headers.set(name, value);
  }
  return headers;
}
