// Same-origin proxy to the Python API (ADR 0006). The browser never learns
// API_ORIGIN or API_PROXY_TOKEN, so there is no CORS surface, the backend can
// move freely, and the hosted API answers only calls that came through here.

import { clientResponseHeaders, upstreamRequestHeaders } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const API_ORIGIN = (process.env.API_ORIGIN ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function forward(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await params;
  const search = new URL(request.url).search;
  const target = `${API_ORIGIN}/api/${path.map(encodeURIComponent).join("/")}${search}`;
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers: upstreamRequestHeaders(request, process.env.API_PROXY_TOKEN),
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return Response.json(
      { detail: "The analysis service is unreachable. Please try again shortly." },
      { status: 502 },
    );
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: clientResponseHeaders(upstream.headers),
  });
}

export { forward as GET, forward as POST, forward as DELETE };
