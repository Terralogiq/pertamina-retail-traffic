import { describe, expect, it } from "vitest";
import type { LatestLeg, Site } from "./api";
import {
  BASELINE_FULL,
  GREY,
  baselineBadge,
  baselineProgress,
  boundsOf,
  congestionColor,
  formatDelay,
  formatSlot,
  indexLatest,
  legColor,
  lineToPath,
  siteLatest,
  sitePoints,
  speedColor,
} from "./bands";

const row = (over: Partial<LatestLeg> = {}): LatestLeg => ({
  selected_route_id: "r1",
  site_id: "s1",
  leg: "approach",
  slot_time: "2026-10-07T07:30:00Z",
  duration_s: 100,
  delay_s: 20,
  congestion_index: 1.0,
  speed_kmh: 40,
  baseline_samples: BASELINE_FULL,
  ...over,
});

const site: Site = {
  site_id: "s1",
  name: "SPBU 1",
  place_id: "p",
  road_name: null,
  city: "Makassar",
  timezone: "Asia/Makassar",
  location: { lat: -5.1, lng: 119.4 },
  legs: [
    {
      selected_route_id: "r1",
      display_name: null,
      side: "spbu_side",
      leg: "approach",
      leg_index: 0,
      expected_distance_m: 500,
      expected_polyline: { type: "LineString", coordinates: [[119.3, -5.2], [119.5, -5.0]] },
    },
    {
      selected_route_id: "r2",
      display_name: null,
      side: "spbu_side",
      leg: "departure",
      leg_index: 1,
      expected_distance_m: 500,
      expected_polyline: null,
    },
  ],
};

describe("congestion bands", () => {
  it("switches colour at 1.2, 1.6 and 2.2", () => {
    const [green, amber, orange, red] = [1.19, 1.2, 1.6, 2.2].map(congestionColor);
    expect(new Set([green, amber, orange, red]).size).toBe(4);
    expect(congestionColor(1.0)).toBe(green);
    expect(congestionColor(1.59)).toBe(amber);
    expect(congestionColor(2.19)).toBe(orange);
    expect(congestionColor(5)).toBe(red);
  });
});

describe("speed bands", () => {
  it("switches colour at 15, 25 and 35 km/h, slow is red", () => {
    expect(speedColor(14.9)).toBe(congestionColor(3));
    expect(speedColor(15)).toBe(congestionColor(1.7));
    expect(speedColor(25)).toBe(congestionColor(1.3));
    expect(speedColor(35)).toBe(congestionColor(1.0));
  });
});

describe("legColor", () => {
  it("uses congestion with a full baseline", () => {
    expect(legColor(row({ congestion_index: 2.5, speed_kmh: 50 }))).toEqual({ color: congestionColor(3), basis: "congestion" });
  });
  it("falls back to speed while the baseline builds", () => {
    expect(legColor(row({ baseline_samples: BASELINE_FULL - 1, congestion_index: 1.0, speed_kmh: 10 }))).toEqual({
      color: speedColor(10),
      basis: "speed",
    });
    expect(legColor(row({ baseline_samples: null, speed_kmh: 10 })).basis).toBe("speed");
  });
  it("is grey without a row or without numbers", () => {
    expect(legColor(undefined)).toEqual({ color: GREY, basis: "none" });
    expect(legColor(row({ congestion_index: null, speed_kmh: null }))).toEqual({ color: GREY, basis: "none" });
    expect(legColor(row({ baseline_samples: 5, speed_kmh: null }))).toEqual({ color: GREY, basis: "none" });
  });
});

describe("latest rows", () => {
  it("keeps the newest slot per leg", () => {
    const m = indexLatest([row({ slot_time: "2026-10-07T07:30:00Z", delay_s: 1 }), row({ slot_time: "2026-10-07T08:00:00Z", delay_s: 2 })]);
    expect(m.get("r1")?.delay_s).toBe(2);
  });
  it("lists rows for a site's legs in leg order", () => {
    const m = indexLatest([row({ selected_route_id: "r2" }), row()]);
    expect(siteLatest(site, m).map((r) => r.selected_route_id)).toEqual(["r1", "r2"]);
    expect(siteLatest(site, new Map())).toEqual([]);
  });
});

describe("baseline badge", () => {
  it("shows the lowest progress over the legs", () => {
    const p = baselineProgress([row({ baseline_samples: 120 }), row({ baseline_samples: 90 })]);
    expect(p).toBe(90);
    expect(baselineBadge(p)).toBe("baseline building (90/336)");
  });
  it("counts a null as 0, caps at the full window and hides when full or without data", () => {
    expect(baselineBadge(baselineProgress([row({ baseline_samples: null })]))).toBe("baseline building (0/336)");
    expect(baselineBadge(baselineProgress([row({ baseline_samples: 400 })]))).toBeNull();
    expect(baselineBadge(baselineProgress([]))).toBeNull();
  });
});

describe("geometry", () => {
  it("converts GeoJSON [lng, lat] to LatLng", () => {
    expect(lineToPath({ coordinates: [[119.3, -5.2], [119.5, -5.0]] })).toEqual([
      { lat: -5.2, lng: 119.3 },
      { lat: -5.0, lng: 119.5 },
    ]);
    expect(lineToPath(null)).toEqual([]);
  });
  it("collects the location and every leg vertex, skipping legs without a polyline", () => {
    expect(sitePoints([site])).toHaveLength(3);
  });
  it("bounds the points; null for none", () => {
    expect(boundsOf(sitePoints([site]))).toEqual({ north: -5.0, south: -5.2, east: 119.5, west: 119.3 });
    expect(boundsOf([])).toBeNull();
  });
});

describe("formatting", () => {
  it("formats delay", () => {
    expect(formatDelay(null)).toBe("-");
    expect(formatDelay(45)).toBe("+45 s");
    expect(formatDelay(90)).toBe("+1.5 min");
    expect(formatDelay(-20)).toBe("-20 s");
  });
  it("shows slot time in the site's local time with a zone label", () => {
    expect(formatSlot("2026-10-07T07:30:00Z", "Asia/Jakarta")).toBe("14:30 WIB");
    expect(formatSlot("2026-10-07T07:30:00Z", "Asia/Makassar")).toBe("15:30 WITA");
  });
});
