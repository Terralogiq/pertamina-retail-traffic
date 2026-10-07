import { beforeEach, describe, expect, it, vi } from "vitest";

const importLibrary = vi.fn(async () => ({}));
const setOptions = vi.fn();
const getConfig = vi.fn();

vi.mock("@googlemaps/js-api-loader", () => ({ importLibrary, setOptions }));
vi.mock("../api", () => ({ getConfig }));

// loadMaps caches its promise at module level: load a fresh copy per test.
const fresh = async () => {
  vi.resetModules();
  return (await import("./maps")).loadMaps();
};

describe("loadMaps map id", () => {
  beforeEach(() => {
    importLibrary.mockClear();
    setOptions.mockClear();
    getConfig.mockReset();
  });

  it("falls back to Google's DEMO_MAP_ID when the server has no Map ID", async () => {
    getConfig.mockResolvedValue({ maps_browser_key: "k" });
    expect((await fresh()).mapId).toBe("DEMO_MAP_ID");
    getConfig.mockResolvedValue({ maps_browser_key: "k", maps_map_id: "" });
    expect((await fresh()).mapId).toBe("DEMO_MAP_ID");
  });

  it("uses the configured Map ID, and passes the key to the loader", async () => {
    getConfig.mockResolvedValue({ maps_browser_key: "k", maps_map_id: "abc123" });
    expect((await fresh()).mapId).toBe("abc123");
    expect(setOptions).toHaveBeenCalledWith({ key: "k", v: "weekly" });
  });
});
