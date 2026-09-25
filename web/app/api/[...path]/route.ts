// Same-origin proxy to the Python API (ADR 0006). The browser never learns
// API_ORIGIN, so there is no CORS surface and the backend can move freely.

export const dynamic = "force-dynamic";
export const maxDuration = 300;

const API_ORIGIN = (process.env.API_ORIGIN ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const FORWARD_RESPONSE_HEADERS = ["content-type", "cache-control", "x-accel-buffering"];

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
      headers: {
        accept: request.headers.get("accept") ?? "application/json",
        ...(hasBody ? { "content-type": request.headers.get("content-type") ?? "application/json" } : {}),
      },
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
  const headers = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}

export { forward as GET, forward as POST, forward as DELETE };
