import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const SITES = [{ site_id: "a" }];

describe("getSites", () => {
  // The shared request is module state: each test gets a fresh copy of the module.
  let getSites: () => Promise<unknown[]>;
  beforeEach(async () => {
    vi.resetModules();
    ({ getSites } = await import("./api"));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shares one request between concurrent callers", async () => {
    const f = vi.fn(async () => Response.json(SITES));
    vi.stubGlobal("fetch", f);
    const [x, y] = await Promise.all([getSites(), getSites()]);
    expect(f).toHaveBeenCalledOnce();
    expect(x).toEqual(SITES);
    expect(y).toBe(x);
  });

  it("fetches again after a failure", async () => {
    const f = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 503 })).mockResolvedValueOnce(Response.json(SITES));
    vi.stubGlobal("fetch", f);
    await expect(getSites()).rejects.toThrow();
    await expect(getSites()).resolves.toEqual(SITES);
    expect(f).toHaveBeenCalledTimes(2);
  });
});
