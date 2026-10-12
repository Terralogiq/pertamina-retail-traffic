import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { LatestLeg, Site } from "./api";
import { BASELINE_FULL } from "./bands";
import Legend from "./Legend";

const site: Site = {
  site_id: "s1",
  name: "SPBU 1",
  place_id: "p",
  road_name: null,
  city: null,
  road_type: "arterial",
  road_class: "urban",
  timezone: "Asia/Jakarta",
  location: { lat: -7, lng: 110 },
  legs: [
    { selected_route_id: "a", display_name: null, side: null, leg: "approach", leg_index: 0, expected_distance_m: 500, expected_polyline: null },
    { selected_route_id: "d", display_name: null, side: null, leg: "departure", leg_index: 1, expected_distance_m: 500, expected_polyline: null },
  ],
};

const row = (id: string, over: Partial<LatestLeg> = {}): LatestLeg => ({
  selected_route_id: id,
  site_id: "s1",
  leg: "approach",
  slot_time: "2026-10-07T06:30:00Z",
  duration_s: 100,
  delay_s: 20,
  congestion_index: 1.0,
  speed_kmh: 40,
  baseline_samples: BASELINE_FULL,
  ...over,
});

const count = (text: string, part: string) => text.split(part).length - 1;
const legend = (rows: LatestLeg[], compact: boolean) =>
  renderToStaticMarkup(<Legend sites={[site]} latest={new Map(rows.map((r) => [r.selected_route_id, r]))} compact={compact} />);

describe("compact Legend", () => {
  const html = legend([row("a"), row("d")], true);

  it("is one row of four bands, not the stacked scales", () => {
    expect(count(html, "<ul")).toBe(1);
    expect(html).toContain("map-legend-row");
    expect(html).not.toContain("map-legend-rows");
    expect(html).not.toContain("map-legend-scale");
    expect(count(html, "<li")).toBe(4);
    for (const label of ["Free flow", "Moderate", "Heavy", "Jammed"]) expect(html).toContain(label);
  });

  it("puts the ranges only in each item's title and visually-hidden text", () => {
    expect(html).toContain('title="under 1.5×, or under the delay gate"');
    expect(html).toContain('title="3× and over"');
    expect(count(html, "under 1.5×, or under the delay gate")).toBe(2);
    expect(count(html, 'class="visually-hidden">(under 1.5×, or under the delay gate)')).toBe(1);
    expect(html).not.toContain("km/h");
  });

  it("adds the provisional note only when a leg is still on provisional usual speed", () => {
    const mixed = legend([row("a"), row("d", { baseline_samples: 5, congestion_index: null })], true);
    expect(mixed).toContain("45 km/h urban");
    expect(mixed).toContain("80 km/h toll");
    const speedOnly = legend([row("a", { baseline_samples: 5 }), row("d", { baseline_samples: 5 })], true);
    expect(speedOnly).toContain("20 s urban or 30 s toll");
    expect(speedOnly).not.toContain("Congestion index");
  });

  it("shows only the no-readings message without data, and the full key is unchanged off compact", () => {
    const none = legend([], true);
    expect(none).toContain("No readings yet");
    expect(none).not.toContain("<li");
    const full = legend([row("a"), row("d")], false);
    expect(full).toContain("map-legend-rows");
    expect(full).not.toContain("map-legend-row\"");
  });
});
