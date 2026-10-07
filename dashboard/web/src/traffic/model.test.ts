import { afterEach, describe, expect, it, vi } from "vitest";
import { getTrafficPattern, getTrafficSeries, TrafficPoint, PatternCell } from "./api";
import type { WeatherSeriesPoint } from "../weather/api";
import {
  emptyCells, formatDelay, hadRain, heatmapData, legSeries, precipitationSeries, tzLabel, utcOffsetMinutes,
  windowStart,
} from "./model";

afterEach(() => vi.unstubAllGlobals());

function pt(leg: string, slot: string, extra: Partial<TrafficPoint> = {}): TrafficPoint {
  return {
    selected_route_id: `r-${leg}`, site_id: "s", leg, slot_time: slot, duration_s: 100, delay_s: 10,
    congestion_index: 1.1, speed_kmh: 30, baseline_samples: 302, ...extra,
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

describe("precipitationSeries", () => {
  const slot = (slot_time: string, precipitation_mm: number | null): WeatherSeriesPoint => ({
    site_id: "s", slot_time, temperature_c: null, relative_humidity: null, precipitation_mm, rain_flag: null,
    wind_speed_kmh: null, demo_rain_flag: null, demo_precip_probability: null,
  });

  it("sorts, drops empty slots and shifts by the same offset as legSeries", () => {
    const rain = precipitationSeries(
      [slot("2026-10-07T01:00:00Z", 0), slot("2026-10-07T00:30:00Z", 1.5), slot("2026-10-07T00:00:00Z", null)],
      480,
    );
    expect(rain).toEqual([
      [Date.parse("2026-10-07T08:30:00Z"), 1.5],
      [Date.parse("2026-10-07T09:00:00Z"), 0],
    ]);
    const line = legSeries([pt("approach", "2026-10-07T00:30:00Z")], "delay_s", 480)[0].data;
    expect(rain[0][0]).toBe(line[0][0]);
  });

  it("is empty without weather", () => {
    expect(precipitationSeries([], 420)).toEqual([]);
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

describe("heatmap and rain helpers", () => {
  it("lists every day x hour without a sample as an empty cell", () => {
    const cells: PatternCell[] = [{ dow: 1, hour: 0, leg: "approach", mean_congestion: 1.2, mean_speed_kmh: null, n: 1 }];
    const empty = emptyCells(cells, "approach");
    expect(empty).toHaveLength(7 * 24 - 1);
    expect(empty).not.toContainEqual([0, 0]);
    expect(emptyCells([], "approach")).toHaveLength(168);
  });

  it("hadRain is false for a window of zeros", () => {
    expect(hadRain([[1, 0], [2, 0]])).toBe(false);
    expect(hadRain([[1, 0], [2, 0.4]])).toBe(true);
    expect(hadRain([])).toBe(false);
  });

  it("formats delay with sign and minutes", () => {
    expect(formatDelay(16.4)).toBe("+16 s");
    expect(formatDelay(75)).toBe("+1 min 15 s");
    expect(formatDelay(-4)).toBe("\u22124 s");
    expect(formatDelay(null)).toBe("n/a");
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
