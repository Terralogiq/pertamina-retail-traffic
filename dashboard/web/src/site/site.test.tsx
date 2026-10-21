import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { LatestLeg, Site } from "../map/api";
import { BASELINE_FULL, legBand } from "../map/bands";
import { BANDS } from "../theme/palette";
import { SECTIONS, StatusStrip, baselineNotice, siteContext } from "./SiteDetail";
import { loadSiteData, siteApi } from "./useSiteData";

const site: Site = {
  site_id: "74.902.22",
  name: "SPBU Pertamina 74.902.22",
  place_id: "p",
  road_name: "Jl. Urip Sumoharjo",
  city: "Makassar",
  road_type: "arterial",
  road_class: "urban",
  timezone: "Asia/Makassar",
  location: { lat: 0, lng: 0 },
  legs: ["approach", "departure"].map((name, i) => ({
    selected_route_id: `r-${name}`,
    display_name: null,
    side: "spbu_side",
    leg: name,
    leg_index: i,
    expected_distance_m: 500,
    expected_polyline: null,
  })),
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
        site={site}
        places={{ site_id: site.site_id, run_id: "r", fetched_at: null, details: { display_name: null, rating: 4.2, user_rating_count: 9, business_status: null, open_now: null, weekday_descriptions: [], reviews: [] }, competitors: [], competitor_totals: [], poi: [] }}
      />,
    );
    expect(html.indexOf("Approach")).toBeLessThan(html.indexOf("Departure"));
    for (const s of ["+16 s", "+1.3 min", "30 km/h", "29.1 °C", "no rain", "4.2"]) expect(html).toContain(s);
    // 500 m at 45 km/h is 40 s; 60 s is 1.5× and 20 s over, so moderate. The label is in the markup.
    expect(html).toContain(BANDS.moderate.label);
  });
});

describe("section nav", () => {
  it("lists the sections in page order: left column (Review themes under Typical day), then right", () => {
    expect(SECTIONS.map((s) => s.label)).toEqual(["Traffic", "Typical day", "Review themes", "Weather", "Places"]);
    expect(SECTIONS.map((s) => s.id)).toEqual(["traffic", "pattern", "review-themes", "weather", "places"]);
  });
});

describe("legBand", () => {
  it("returns the band id with its basis", () => {
    expect(legBand(undefined)).toEqual({ band: "none", basis: "none" });
    expect(legBand(leg("approach", { duration_s: 180, baseline_samples: 10 }), { roadClass: "urban", expectedDistanceM: 500 })).toEqual({
      band: "jam",
      basis: "speed",
    });
    expect(legBand(leg("approach", { baseline_samples: BASELINE_FULL, congestion_index: 1.1, delay_s: 16 }))).toEqual({
      band: "free",
      basis: "congestion",
    });
  });
});

describe("loadSiteData", () => {
  const fakeApi = (sites: Site[] | Error) => ({
    getSites: vi.fn(() => (sites instanceof Error ? Promise.reject(sites) : Promise.resolve(sites))),
    getLatestTraffic: vi.fn(() => Promise.resolve([leg("approach")])),
    getWeatherLatest: vi.fn(() => Promise.resolve([])),
    getPlaces: vi.fn(() => Promise.resolve(null as never)),
    getAiSummary: vi.fn(() => Promise.resolve({ site_id: "74.902.22", summary: null })),
  }) satisfies typeof siteApi;
  const run = async (siteId: string, api: ReturnType<typeof fakeApi>) => {
    const got: Record<string, unknown> = {};
    await loadSiteData(siteId, (key) => (v) => void (got[key] = v), api);
    await new Promise((r) => setTimeout(r)); // let the panel requests settle
    return got;
  };

  it("fires no traffic, weather or Places request for an unknown code", async () => {
    const api = fakeApi([site]);
    expect(await run("nope", api)).toEqual({ site: null });
    expect(api.getSites).toHaveBeenCalledTimes(1);
    expect(api.getLatestTraffic).not.toHaveBeenCalled();
    expect(api.getWeatherLatest).not.toHaveBeenCalled();
    expect(api.getPlaces).not.toHaveBeenCalled();
    expect(api.getAiSummary).not.toHaveBeenCalled();
  });

  it("fires no panel request when /api/sites fails, and reports the error", async () => {
    const api = fakeApi(new Error("down"));
    const got = await run(site.site_id, api);
    expect(got.site).toBeInstanceOf(Error);
    expect(api.getLatestTraffic).not.toHaveBeenCalled();
    expect(api.getPlaces).not.toHaveBeenCalled();
  });

  it("starts the panel requests once the site exists", async () => {
    const api = fakeApi([site]);
    const got = await run(site.site_id, api);
    expect(got.site).toEqual(site);
    expect(got.legs).toHaveLength(1);
    expect(api.getWeatherLatest).toHaveBeenCalledTimes(1);
    expect(api.getPlaces).toHaveBeenCalledWith(site.site_id);
    // one AI summary request for the four section cards; no summary in the slot is null, not an error
    expect(api.getAiSummary).toHaveBeenCalledTimes(1);
    expect(api.getAiSummary).toHaveBeenCalledWith(site.site_id);
    expect(got.summary).toBeNull();
  });

  it("reports a failed AI summary request without touching the other parts", async () => {
    const api = fakeApi([site]);
    api.getAiSummary.mockImplementation(() => Promise.reject(new Error("down")));
    const got = await run(site.site_id, api);
    expect(got.summary).toBeInstanceOf(Error);
    expect(got.legs).toHaveLength(1);
  });
});
