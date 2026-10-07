import { afterEach, describe, expect, it, vi } from "vitest";
import { getTrafficPattern, getTrafficSeries, TrafficPoint, PatternCell } from "./api";
import { baselineBuilding, heatmapData, legSeries, tzLabel, utcOffsetMinutes, windowStart } from "./model";

afterEach(() => vi.unstubAllGlobals());

function pt(leg: string, slot: string, extra: Partial<TrafficPoint> = {}): TrafficPoint {
  return {
    selected_route_id: `r-${leg}`, site_id: "s", leg, slot_time: slot, duration_s: 100, delay_s: 10,
    congestion_index: 1.1, speed_kmh: 30, baseline_samples: 336, ...extra,
  };
}

describe("time zones", () => {
  it("labels WIB and WITA", () => {
    expect(tzLabel("Asia/Jakarta")).toBe("WIB");
    expect(tzLabel("Asia/Makassar")).toBe("WITA");
    expect(tzLabel(null)).toBe("UTC");
  });

  it("computes the UTC offset per zone", () => {
    const at = new Date("2026-10-07T00:00:00Z");
    expect(utcOffsetMinutes("Asia/Jakarta", at)).toBe(420);
    expect(utcOffsetMinutes("Asia/Makassar", at)).toBe(480);
    expect(utcOffsetMinutes(null, at)).toBe(0);
    expect(utcOffsetMinutes("Not/AZone", at)).toBe(0);
  });
});

describe("windowStart", () => {
  const now = new Date("2026-10-07T10:47:12Z");
  it("floors to the half hour", () => {
    expect(windowStart("24h", now)).toBe("2026-10-06T10:30:00.000Z");
    expect(windowStart("7d", now)).toBe("2026-09-30T10:30:00.000Z");
  });
});

describe("legSeries", () => {
  it("groups by leg, sorts by time and shifts to site-local time", () => {
    const points = [
      pt("approach", "2026-10-07T01:00:00Z"),
      pt("departure", "2026-10-07T00:30:00Z", { delay_s: null }),
      pt("approach", "2026-10-07T00:30:00Z", { delay_s: 5 }),
    ];
    const lines = legSeries(points, "delay_s", 480);
    expect(lines.map((l) => l.leg)).toEqual(["approach", "departure"]);
    expect(lines[0].data).toEqual([
      [Date.parse("2026-10-07T08:30:00Z"), 5],
      [Date.parse("2026-10-07T09:00:00Z"), 10],
    ]);
    expect(lines[1].data).toEqual([[Date.parse("2026-10-07T08:30:00Z"), null]]);
  });
});

describe("baselineBuilding", () => {
  it("returns the smallest sample count of the legs' latest slots while under 336", () => {
    const points = [
      pt("approach", "2026-10-07T00:00:00Z", { baseline_samples: 10 }),
      pt("approach", "2026-10-07T00:30:00Z", { baseline_samples: 100 }),
      pt("departure", "2026-10-07T00:30:00Z", { baseline_samples: 90 }),
    ];
    expect(baselineBuilding(points)).toBe(90);
  });

  it("counts a missing baseline as 0 and is null once the window is full or empty", () => {
    expect(baselineBuilding([pt("approach", "2026-10-07T00:00:00Z", { baseline_samples: null })])).toBe(0);
    expect(baselineBuilding([pt("approach", "2026-10-07T00:00:00Z", { baseline_samples: 336 })])).toBeNull();
    expect(baselineBuilding([])).toBeNull();
  });
});

describe("heatmapData", () => {
  it("keeps one leg as [hour, dow - 1, mean] and drops empty cells", () => {
    const cell = (leg: string, mean: number | null): PatternCell =>
      ({ dow: 7, hour: 8, leg, mean_congestion: mean, mean_speed_kmh: null, n: 3 });
    expect(heatmapData([cell("approach", 1.5), cell("departure", 2), cell("approach", null)], "approach")).toEqual([
      [8, 6, 1.5],
    ]);
  });
});

describe("api client", () => {
  it("builds the series and pattern URLs", async () => {
    const f = vi.fn().mockImplementation(() => Promise.resolve(Response.json([])));
    vi.stubGlobal("fetch", f);
    await getTrafficSeries("74.902.22", "2026-10-06T10:30:00.000Z");
    await getTrafficPattern("74.902.22");
    expect(f.mock.calls[0][0]).toBe("/api/traffic/series?site_id=74.902.22&from=2026-10-06T10%3A30%3A00.000Z");
    expect(f.mock.calls[1][0]).toBe("/api/traffic/pattern?site_id=74.902.22&days=28");
  });
});
