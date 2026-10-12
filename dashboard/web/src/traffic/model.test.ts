import { afterEach, describe, expect, it, vi } from "vitest";
import { getTrafficPattern, getTrafficSeries, getTypicalDay, TrafficPoint } from "./api";
import type { WeatherSeriesPoint } from "../weather/api";
import {
  delaySeries, delayTooltipText, formatDelay, hadRain, legSeries, precipitationSeries, tzLabel, utcOffsetMinutes,
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

describe("delaySeries", () => {
  it("keeps speed and the usual-time multiple beside the plotted delay", () => {
    const lines = delaySeries([
      pt("approach", "2026-10-07T00:30:00Z", { delay_s: 20, speed_kmh: 28, congestion_index: 1.5 }),
      pt("approach", "2026-10-07T01:00:00Z", { delay_s: null, speed_kmh: null, congestion_index: null }),
    ], 480);
    expect(lines).toHaveLength(1);
    expect(lines[0].data[0]).toEqual({
      value: [Date.parse("2026-10-07T08:30:00Z"), 20],
      speed_kmh: 28,
      congestion_index: 1.5,
    });
    expect(lines[0].data[1].value[1]).toBeNull();
  });
});

describe("delay tooltip", () => {
  it("names the delay, the speed and how many times the usual travel time", () => {
    expect(delayTooltipText("Approach", 20, 28, 1.5)).toBe("Approach: +20 s · 28 km/h · 1.50× usual time");
    expect(delayTooltipText("Departure", -4, null, null)).toBe("Departure: -4 s · n/a · n/a");
    expect(delayTooltipText("Approach", null, 30, 1.2)).toBe("Approach: n/a · 30 km/h · 1.20× usual time");
  });
});

describe("rain helpers", () => {
  it("hadRain is false for a window of zeros", () => {
    expect(hadRain([[1, 0], [2, 0]])).toBe(false);
    expect(hadRain([[1, 0], [2, 0.4]])).toBe(true);
    expect(hadRain([])).toBe(false);
  });

  it("formats delay with sign and minutes", () => {
    expect(formatDelay(16.4)).toBe("+16 s");
    expect(formatDelay(75)).toBe("+1.3 min");
    expect(formatDelay(-4)).toBe("-4 s");
    expect(formatDelay(null)).toBe("-");
  });
});

describe("api client", () => {
  it("builds the series, pattern and typical-day URLs", async () => {
    const f = vi.fn().mockImplementation(() => Promise.resolve(Response.json([])));
    vi.stubGlobal("fetch", f);
    await getTrafficSeries("74.902.22", "2026-10-06T10:30:00.000Z");
    await getTrafficPattern("74.902.22");
    await getTypicalDay("74.902.22");
    expect(f.mock.calls[0][0]).toBe("/api/traffic/series?site_id=74.902.22&from=2026-10-06T10%3A30%3A00.000Z");
    expect(f.mock.calls[1][0]).toBe("/api/traffic/pattern?site_id=74.902.22&days=28");
    expect(f.mock.calls[2][0]).toBe("/api/traffic/typical-day?site_id=74.902.22");
  });
});
