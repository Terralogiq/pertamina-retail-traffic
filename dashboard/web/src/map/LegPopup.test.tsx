import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { LatestLeg, Leg, Site } from "./api";
import { BASELINE_FULL } from "./bands";
import { GROUP_POPUP_MAX, GroupPopup, LegPopup, SitePopup, buildGroupPopup, buildLegPopup, buildSitePopup } from "./LegPopup";
import { rankSites } from "./severity";

const leg = (name: "approach" | "departure"): Leg => ({
  selected_route_id: `r-${name}`,
  display_name: null,
  side: "spbu_side",
  leg: name,
  leg_index: name === "approach" ? 0 : 1,
  expected_distance_m: 500,
  expected_polyline: null,
});

const site = (timezone: string): Site => ({
  site_id: "s1",
  name: "SPBU Pertamina 3440116",
  place_id: "p",
  road_name: null,
  city: null,
  timezone,
  location: { lat: -7, lng: 110 },
  legs: [leg("approach"), leg("departure")],
});

const row = (over: Partial<LatestLeg> = {}): LatestLeg => ({
  selected_route_id: "r-departure",
  site_id: "s1",
  leg: "departure",
  slot_time: "2026-10-07T06:30:00Z",
  duration_s: 100,
  delay_s: 66,
  congestion_index: 1.0,
  speed_kmh: 18.4,
  baseline_samples: BASELINE_FULL,
  ...over,
});

describe("buildLegPopup", () => {
  it("builds the view model for a leg with a full baseline", () => {
    expect(buildLegPopup(site("Asia/Jakarta"), leg("departure"), row({ congestion_index: 1.7 }))).toEqual({
      overline: "Departure · away from the SPBU",
      title: "SPBU Pertamina 3440116",
      band: "heavy",
      bandLabel: "Heavy",
      delay: "+1.1 min",
      speed: "18 km/h",
      slot: "13:30 WIB",
      basis: null,
    });
  });

  it("says the band comes from speed while the baseline builds", () => {
    const model = buildLegPopup(site("Asia/Jakarta"), leg("departure"), row({ baseline_samples: 10, congestion_index: null }));
    expect(model.band).toBe("heavy"); // 18 km/h: 15 to 25
    expect(model.basis).toBe("Band from speed while the baseline builds");
  });

  it("shows the slot in the site's local time (WITA)", () => {
    const model = buildLegPopup(site("Asia/Makassar"), leg("approach"), row());
    expect(model.slot).toBe("14:30 WITA");
    expect(model.overline).toBe("Approach · toward the SPBU");
  });

  it("keeps the card complete when speed and delay are null", () => {
    const model = buildLegPopup(site("Asia/Jakarta"), leg("departure"), row({ delay_s: null, speed_kmh: null, congestion_index: null }));
    expect(model).toMatchObject({ band: "none", bandLabel: "No data", delay: "-", speed: "-", slot: "13:30 WIB", basis: null });
  });

  it("has no slot and no band without a reading", () => {
    expect(buildLegPopup(site("Asia/Jakarta"), leg("departure"), undefined)).toMatchObject({
      band: "none",
      delay: "-",
      speed: "-",
      slot: null,
      basis: null,
    });
  });
});

describe("LegPopup", () => {
  const model = buildLegPopup(site("Asia/Jakarta"), leg("departure"), row({ baseline_samples: 10, congestion_index: null }));

  it("renders the hierarchy with the band label and no close button on hover", () => {
    const html = renderToStaticMarkup(<LegPopup model={model} />);
    expect(html).toContain('role="tooltip"');
    expect(html).toContain("Departure · away from the SPBU");
    expect(html).toContain("SPBU Pertamina 3440116");
    expect(html).toContain("Heavy");
    expect(html).toContain("+1.1 min");
    expect(html).toContain("Speed 18 km/h");
    expect(html).toContain("Slot 13:30 WIB");
    expect(html).toContain("Band from speed while the baseline builds");
    expect(html).not.toContain("<button");
  });

  it("adds a labelled close button and becomes a named dialog when pinned", () => {
    const html = renderToStaticMarkup(<LegPopup model={model} onClose={() => {}} />);
    expect(html).toContain('aria-label="Close"');
    expect(html).toContain("data-pinned");
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-label="SPBU Pertamina 3440116"');
    expect(html).not.toContain('role="tooltip"');
  });

  it("pins a site card with a close button too", () => {
    const html = renderToStaticMarkup(<SitePopup model={buildSitePopup(site("Asia/Jakarta"), new Map())} onClose={() => {}} />);
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-label="Close"');
  });

  it("omits the slot when there is no reading", () => {
    const html = renderToStaticMarkup(<LegPopup model={buildLegPopup(site("Asia/Jakarta"), leg("departure"), undefined)} />);
    expect(html).not.toContain("Slot");
  });
});

const withRows = (rows: LatestLeg[]) => new Map(rows.map((r) => [r.selected_route_id, r]));

describe("buildSitePopup", () => {
  const full = { ...site("Asia/Makassar"), city: "Makassar", road_name: "Jl. Perintis" };

  it("lists one reading per leg and the newest slot in site local time", () => {
    const latest = withRows([
      row({ selected_route_id: "r-approach", leg: "approach", delay_s: 20, congestion_index: 1.0, slot_time: "2026-10-07T06:00:00Z" }),
      row({ selected_route_id: "r-departure", delay_s: 150, congestion_index: 2.3, slot_time: "2026-10-07T06:30:00Z" }),
    ]);
    expect(buildSitePopup(full, latest)).toEqual({
      overline: "Makassar · Jl. Perintis",
      title: "SPBU Pertamina 3440116",
      legs: [
        { name: "Approach", band: "free", bandLabel: "Free flow", delay: "+20 s" },
        { name: "Departure", band: "jam", bandLabel: "Jammed", delay: "+2.5 min" },
      ],
      slot: "14:30 WITA",
    });
  });

  it("copes with missing city, road and readings", () => {
    const model = buildSitePopup(site("Asia/Jakarta"), new Map());
    expect(model.overline).toBeNull();
    expect(model.slot).toBeNull();
    expect(model.legs).toEqual([
      { name: "Approach", band: "none", bandLabel: "No data", delay: "-" },
      { name: "Departure", band: "none", bandLabel: "No data", delay: "-" },
    ]);
    expect(buildSitePopup({ ...site("Asia/Jakarta"), city: "Bandung" }, new Map()).overline).toBe("Bandung");
  });

  it("renders the legs and slot, with no close button", () => {
    const html = renderToStaticMarkup(<SitePopup model={buildSitePopup(full, withRows([row({ selected_route_id: "r-approach" })]))} />);
    expect(html).toContain("Makassar · Jl. Perintis");
    expect(html).toContain("Approach");
    expect(html).toContain("Slot 14:30 WITA");
    expect(html).not.toContain("<button");
  });
});

describe("buildGroupPopup", () => {
  const sites = (n: number): Site[] =>
    Array.from({ length: n }, (_, i) => ({ ...site("Asia/Jakarta"), site_id: `s${i}`, name: `SPBU ${i}`, legs: [{ ...leg("departure"), selected_route_id: `r${i}` }] }));
  const latestFor = (list: Site[]) =>
    withRows(list.map((s, i) => row({ selected_route_id: s.legs[0].selected_route_id, site_id: s.site_id, delay_s: i * 60, congestion_index: 1 + i * 0.5 })));

  it("lists the grouped sites worst first with their band and delay", () => {
    const list = sites(3);
    const model = buildGroupPopup(rankSites(list, latestFor(list)));
    expect(model.title).toBe("3 sites");
    expect(model.sites).toEqual([
      { name: "SPBU 2", band: "heavy", bandLabel: "Heavy", delay: "+2.0 min" },
      { name: "SPBU 1", band: "moderate", bandLabel: "Moderate", delay: "+1.0 min" },
      { name: "SPBU 0", band: "free", bandLabel: "Free flow", delay: "+0 s" },
    ]);
    expect(model.more).toBe(0);
  });

  it("caps the list and counts the rest; a silent site shows no data", () => {
    const list = sites(GROUP_POPUP_MAX + 2);
    const model = buildGroupPopup(rankSites(list, new Map()));
    expect(model.sites).toHaveLength(GROUP_POPUP_MAX);
    expect(model.more).toBe(2);
    expect(model.sites[0]).toMatchObject({ band: "none", bandLabel: "No data", delay: "-" });
    const html = renderToStaticMarkup(<GroupPopup model={model} />);
    expect(html).toContain("and 2 more");
    expect(html).toContain("Click to zoom in");
  });
});
