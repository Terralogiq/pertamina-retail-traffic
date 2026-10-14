import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Site } from "../map/api";
import type { TrafficPoint, TypicalHour, TypicalLeg } from "./api";
import { TrafficTable, TypicalDayTable, ViewToggle } from "./ChartTable";

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

const TOLL_SITE: Site = {
  ...SITE,
  road_type: "toll rest area",
  road_class: "toll",
};

describe("ChartTable", () => {
  it("toggles between chart and table", () => {
    const html = renderToStaticMarkup(<ViewToggle mode="table" onChange={() => undefined} />);
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("Chart");
    expect(html).toContain("Table");
  });

  it("renders one traffic table row per point with the band label", () => {
    const points: TrafficPoint[] = [
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
        slot_time: "2026-10-08T12:30:00Z",
        duration_s: 80,
        delay_s: 10,
        congestion_index: 1.2,
        speed_kmh: 35,
        baseline_samples: 302,
      },
    ];
    const html = renderToStaticMarkup(<TrafficTable points={points} timezone="Asia/Jakarta" site={SITE} />);
    const rows = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/)?.[1] ?? "";
    expect(rows.match(/<tr>/g)?.length).toBe(2);
    expect(html).toContain("Approach");
    expect(html).toContain("Departure");
    expect(html).toContain("+20 s");
    expect(html).toContain("Moderate");
    expect(html).toContain("28 km/h");
    // 7 Oct vs 8 Oct in Asia/Jakarta (UTC+7)
    expect(html).toContain("7 Oct");
    expect(html).toContain("8 Oct");
  });

  it("uses the toll delay gate for a toll site", () => {
    const points: TrafficPoint[] = [
      {
        selected_route_id: "r-approach",
        site_id: "s",
        leg: "approach",
        slot_time: "2026-10-07T12:00:00Z",
        duration_s: 100,
        delay_s: 25,
        congestion_index: 1.5,
        speed_kmh: 28,
        baseline_samples: 302,
      },
    ];
    const urban = renderToStaticMarkup(<TrafficTable points={points} timezone="Asia/Jakarta" site={SITE} />);
    const toll = renderToStaticMarkup(<TrafficTable points={points} timezone="Asia/Jakarta" site={TOLL_SITE} />);
    expect(urban).toContain("Moderate");
    expect(toll).toContain("Free flow");
  });

  it("renders one typical-day table row per hour", () => {
    const hours: TypicalHour[] = [
      { hour: 8, median_delay_s: 40, p25_delay_s: 30, p75_delay_s: 50, n: 6, faded: false, busy: true },
      { hour: 9, median_delay_s: null, p25_delay_s: null, p75_delay_s: null, n: 0, faded: true, busy: false },
    ];
    const leg: TypicalLeg = { leg: "approach", day_kind: "weekday", hours, windows: [] };
    const html = renderToStaticMarkup(<TypicalDayTable legs={[leg]} />);
    const rows = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/)?.[1] ?? "";
    expect(rows.match(/<tr>/g)?.length).toBe(1);
    expect(html).toContain("08:00");
    expect(html).toContain("Approach");
    expect(html).toContain("+40 s");
    expect(html).toContain("Yes");
    expect(html).not.toContain("09:00");
  });
});
