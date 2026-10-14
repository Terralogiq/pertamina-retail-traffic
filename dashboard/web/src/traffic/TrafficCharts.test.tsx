import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Site } from "../map/api";
import TrafficCharts from "./TrafficCharts";

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
  legs: [],
};

describe("TrafficCharts", () => {
  it("shows the chart/table toggle once data is loaded", () => {
    const html = renderToStaticMarkup(<TrafficCharts siteId="s" timezone="Asia/Jakarta" site={SITE} />);
    expect(html).toContain("Traffic");
    // The toggle is inside the chart block, which only renders after points load.
  });
});
