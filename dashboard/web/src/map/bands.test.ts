import { describe, expect, it } from "vitest";
import type { LatestLeg, Site } from "./api";
import {
  BASELINE_FULL,
  GREY,
  bandOf,
  baselineProgress,
  boundsOf,
  formatDelay,
  formatSlot,
  indexLatest,
  legBand,
  legColor,
  lineToPath,
  roadClassOf,
  sitePoints,
} from "./bands";
import { BANDS } from "../theme/palette";

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
  road_type: "arterial",
  road_class: "urban",
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

const urban = { roadClass: "urban" as const, expectedDistanceM: 500 };
const toll = { roadClass: "toll" as const, expectedDistanceM: 500 };

describe("band rule", () => {
  const examples: [number, number, "urban" | "toll", string][] = [
    [1.4, 40, "urban", "free"],
    [1.6, 15, "urban", "free"],
    [1.6, 25, "urban", "moderate"],
    [2.2, 25, "urban", "heavy"],
    [3.1, 40, "urban", "jam"],
    [2.5, 15, "urban", "free"],
    [1.8, 25, "toll", "free"],
    [1.8, 35, "toll", "moderate"],
  ];
  it.each(examples)("index %s, delay %ss, %s → %s", (index, delay, road, band) => {
    expect(bandOf(index, delay, road)).toBe(band);
  });

  it("treats a toll mention as toll and every other label as urban", () => {
    expect(roadClassOf("toll rest area")).toBe("toll");
    expect(roadClassOf("congested arterial")).toBe("urban");
    expect(roadClassOf(null)).toBe("urban");
  });
});

describe("legColor", () => {
  it("uses congestion with a full baseline", () => {
    expect(legColor(row({ congestion_index: 2.5, delay_s: 40 }), urban)).toEqual({ color: BANDS.heavy.color, basis: "congestion" });
  });
  it("uses the provisional speed while the baseline builds", () => {
    // 500 m at 45 km/h is 40 s. 60 s is 1.5× and 20 s over, so moderate.
    expect(legColor(row({ baseline_samples: BASELINE_FULL - 1, duration_s: 60 }), urban)).toEqual({
      color: BANDS.moderate.color,
      basis: "speed",
    });
    // 500 m at 80 km/h is 22.5 s. 50 s is 2.2× but only 27.5 s over, under the 30 s toll gate, so free.
    expect(legBand(row({ baseline_samples: null, duration_s: 50 }), toll)).toEqual({ band: "free", basis: "speed" });
  });
  it("is grey without a row or without numbers", () => {
    expect(legColor(undefined)).toEqual({ color: GREY, basis: "none" });
    expect(legColor(row({ congestion_index: null, speed_kmh: null }))).toEqual({ color: GREY, basis: "none" });
    expect(legColor(row({ baseline_samples: 5, duration_s: null }), urban)).toEqual({ color: GREY, basis: "none" });
  });
});

describe("legBand", () => {
  it("names the band and its basis", () => {
    expect(legBand(row({ congestion_index: 1.0, delay_s: 40 }))).toEqual({ band: "free", basis: "congestion" });
    expect(legBand(row({ congestion_index: 1.6, delay_s: 25 }))).toEqual({ band: "moderate", basis: "congestion" });
    expect(legBand(row({ congestion_index: 3.1, delay_s: 40 }))).toEqual({ band: "jam", basis: "congestion" });
    expect(legBand(row({ baseline_samples: 10, duration_s: 90 }), urban)).toEqual({ band: "heavy", basis: "speed" });
    expect(legBand(row({ baseline_samples: 10, duration_s: 45 }), urban)).toEqual({ band: "free", basis: "speed" });
    expect(legBand(undefined)).toEqual({ band: "none", basis: "none" });
  });
});

describe("latest rows", () => {
  it("keeps the newest slot per leg", () => {
    const m = indexLatest([row({ slot_time: "2026-10-07T07:30:00Z", delay_s: 1 }), row({ slot_time: "2026-10-07T08:00:00Z", delay_s: 2 })]);
    expect(m.get("r1")?.delay_s).toBe(2);
  });
});

describe("baselineProgress", () => {
  it("is the lowest progress over the legs", () => {
    expect(baselineProgress([row({ baseline_samples: 120 }), row({ baseline_samples: 90 })])).toBe(90);
  });
  it("counts a null as 0, caps at the full window and is null without data", () => {
    expect(baselineProgress([row({ baseline_samples: null })])).toBe(0);
    expect(baselineProgress([row({ baseline_samples: 400 })])).toBe(BASELINE_FULL);
    expect(baselineProgress([])).toBeNull();
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
