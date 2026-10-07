import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { LatestLeg, Site } from "../map/api";
import { BASELINE_FULL } from "../map/bands";
import { BANDS } from "../theme/palette";
import { legBand } from "../map/bands";
import { StatusStrip, baselineNotice, siteContext } from "./SiteDetail";

const site: Site = {
  site_id: "74.902.22",
  name: "SPBU Pertamina 74.902.22",
  place_id: "p",
  road_name: "Jl. Urip Sumoharjo",
  city: "Makassar",
  timezone: "Asia/Makassar",
  location: { lat: 0, lng: 0 },
  legs: [],
};

const leg = (name: string, extra: Partial<LatestLeg> = {}): LatestLeg => ({
  selected_route_id: `r-${name}`,
  site_id: site.site_id,
  leg: name,
  slot_time: "2026-10-07T03:00:00Z",
  duration_s: 60,
  delay_s: 16,
  congestion_index: 1.4,
  speed_kmh: 30,
  baseline_samples: 27,
  ...extra,
});

describe("site header", () => {
  it("puts the code, city, road and local zone after the name", () => {
    expect(siteContext(site)).toBe("SPBU 74.902.22 · Makassar · Jl. Urip Sumoharjo · WITA");
    expect(siteContext({ ...site, road_name: null })).toBe("SPBU 74.902.22 · Makassar · WITA");
  });

  it("explains the provisional baseline only while it is building", () => {
    expect(baselineNotice([leg("approach"), leg("departure", { baseline_samples: 40 })])).toContain(`27 of ${BASELINE_FULL}`);
    expect(baselineNotice([leg("approach", { baseline_samples: BASELINE_FULL })])).toBeNull();
    expect(baselineNotice([])).toBeNull();
  });

  it("status strip shows each leg's delay with a band label, the weather and the rating", () => {
    const html = renderToStaticMarkup(
      <StatusStrip
        legs={[leg("departure", { delay_s: 75 }), leg("approach")]}
        weather={{
          site_id: site.site_id, slot_time: "", temperature_c: 29.14, relative_humidity: null, precipitation_mm: 0,
          rain_flag: false, wind_speed_kmh: null, demo_condition_type: null, demo_condition_text: null,
          demo_icon_uri: null, demo_rain_flag: null, demo_precip_probability: null,
        }}
        places={{ site_id: site.site_id, run_id: "r", fetched_at: null, details: { display_name: null, rating: 4.2, user_rating_count: 9, business_status: null, open_now: null, weekday_descriptions: [], reviews: [] }, competitors: [], competitor_totals: [], poi: [] }}
      />,
    );
    expect(html.indexOf("Approach")).toBeLessThan(html.indexOf("Departure"));
    for (const s of ["+16 s", "+1 min 15 s", "30 km/h", "29.1 °C", "no rain", "4.2"]) expect(html).toContain(s);
    // colour is never the only signal: the band label is in the markup (speed fallback, 30 km/h = moderate)
    expect(html).toContain(BANDS.moderate.label);
  });
});

describe("legBand shim", () => {
  it("maps legColor to a band id with its basis", () => {
    expect(legBand(undefined)).toEqual({ band: "none", basis: "none" });
    expect(legBand(leg("approach", { speed_kmh: 10 }))).toEqual({ band: "jam", basis: "speed" });
    expect(legBand(leg("approach", { baseline_samples: BASELINE_FULL, congestion_index: 1.1 }))).toEqual({
      band: "free",
      basis: "congestion",
    });
  });
});
