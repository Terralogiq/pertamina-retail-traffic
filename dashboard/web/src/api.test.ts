import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, UnauthorizedError, errorText, getJson, login, setUnauthorizedHandler } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  setUnauthorizedHandler(() => {});
});

describe("api client", () => {
  it("calls the unauthorized handler and throws on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    await expect(getJson("/api/sites")).rejects.toBeInstanceOf(UnauthorizedError);
    expect(handler).toHaveBeenCalledOnce();
  });

  it("returns parsed JSON on 200", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json([{ site_id: "a" }])));
    await expect(getJson("/api/sites")).resolves.toEqual([{ site_id: "a" }]);
  });

  it("shares one request between concurrent calls for a path and fetches again once it settled", async () => {
    const f = vi.fn(async () => Response.json({ days: 3 }));
    vi.stubGlobal("fetch", f);
    const [a, b] = await Promise.all([getJson("/api/traffic/typical-day?site_id=1"), getJson("/api/traffic/typical-day?site_id=1")]);
    expect(a).toEqual({ days: 3 });
    expect(b).toBe(a);
    expect(f).toHaveBeenCalledTimes(1);
    await getJson("/api/traffic/typical-day?site_id=1");
    await Promise.all([getJson("/api/traffic/typical-day?site_id=2"), getJson("/api/traffic/typical-day?site_id=3")]);
    expect(f).toHaveBeenCalledTimes(4);
  });

  it("does not keep a failed request: the next call retries", async () => {
    const f = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 503 })).mockResolvedValueOnce(Response.json([1]));
    vi.stubGlobal("fetch", f);
    await expect(getJson("/api/rain")).rejects.toBeInstanceOf(ApiError);
    await expect(getJson("/api/rain")).resolves.toEqual([1]);
  });

  it("login resolves false on a wrong password and true on 204", async () => {
    const f = vi.fn().mockResolvedValueOnce(new Response(null, { status: 401 }));
    f.mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", f);
    await expect(login("bad")).resolves.toBe(false);
    await expect(login("good")).resolves.toBe(true);
  });
});

describe("ApiError", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("words server and network failures for the reader, without the request URL", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 503 })));
    const err = await getJson("/api/traffic/latest").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(errorText(err)).toBe("The server had a problem (HTTP 503). Try again in a minute.");
    expect(errorText(err)).not.toContain("/api/");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    expect(errorText(await getJson("/api/sites").catch((e) => e))).toMatch(/^No connection/);
  });
});
