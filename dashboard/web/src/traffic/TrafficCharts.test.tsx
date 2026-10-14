import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Site } from "../map/api";
import type { TrafficPoint } from "./api";
import TrafficCharts, { TrafficChartsBody } from "./TrafficCharts";

const SITE: Site = {
  site_id: "s",
  name: "Site",
  place_id: "p",
  road_name: "Road",
  city: "City",
  road_type: "arterial",
  road_class: "urban",
  timezone: "Asia/Jakarta",
  location: { lat: 0, lng: 0 },
  legs: [
    { selected_route_id: "r-approach", display_name: "A", side: "spbu_side", leg: "approach", leg_index: 0, expected_distance_m: 500, expected_polyline: null },
    { selected_route_id: "r-departure", display_name: "D", side: "spbu_side", leg: "departure", leg_index: 1, expected_distance_m: 500, expected_polyline: null },
  ],
};

const POINTS: TrafficPoint[] = [
  {
    selected_route_id: "r-approach",
    site_id: "s",
    leg: "approach",
    slot_time: "2026-10-07T12:00:00Z",
    duration_s: 100,
    delay_s: 20,
    congestion_index: 1.5,
    speed_kmh: 28,
    baseline_samples: 302,
  },
  {
    selected_route_id: "r-departure",
    site_id: "s",
    leg: "departure",
    slot_time: "2026-10-07T12:30:00Z",
    duration_s: 80,
    delay_s: 10,
    congestion_index: 1.2,
    speed_kmh: 35,
    baseline_samples: 302,
  },
];

describe("TrafficCharts", () => {
  it("renders the loading skeleton before points arrive", () => {
    const html = renderToStaticMarkup(<TrafficCharts siteId="s" timezone="Asia/Jakarta" site={SITE} />);
    expect(html).toContain("Loading delay");
  });
});

describe("TrafficChartsBody", () => {
  it("shows the chart/table toggle and one table row per point", () => {
    const html = renderToStaticMarkup(
      <TrafficChartsBody
        delay={null as never}
        rainChart={null}
        points={POINTS}
        weather={null}
        rainError=""
        legs={["approach", "departure"]}
        site={SITE}
        timezone="Asia/Jakarta"
        group="traffic-s"
        windowLabel="last 24 hours"
        view="table"
        onViewChange={() => undefined}
      />,
    );
    expect(html).toContain('aria-label="View"');
    expect(html).toContain("Chart");
    expect(html).toContain("Table");
    const rows = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/)?.[1] ?? "";
    expect(rows.match(/<tr>/g)?.length).toBe(2);
  });
});
