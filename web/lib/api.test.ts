import { afterEach, describe, expect, it, vi } from "vitest";
import { getMeta } from "./api";

describe("getMeta", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch() {
    const fetch = vi.fn(async () => new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    return fetch;
  }

  it("names the runtime whose snapshot banner it wants", async () => {
    const fetch = stubFetch();
    await getMeta("live");
    expect(fetch).toHaveBeenCalledWith("/api/meta?runtime=live", expect.anything());
  });

  it("leaves the runtime to the deployment when none is named", async () => {
    const fetch = stubFetch();
    await getMeta();
    expect(fetch).toHaveBeenCalledWith("/api/meta", expect.anything());
  });
});
