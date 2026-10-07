import { describe, expect, it } from "vitest";
import type { LatestLeg, Site } from "./api";
import { BASELINE_FULL, indexLatest } from "./bands";
import { baselineDaysLeft, clusterPoints, orderSites, rankSites, summarize } from "./severity";

const mkSite = (id: string, name: string, lat: number, lng: number): Site => ({
  site_id: id,
  name,
  place_id: id,
  road_name: null,
  city: null,
  timezone: "Asia/Jakarta",
  location: { lat, lng },
  legs: ["approach", "departure"].map((leg, i) => ({
    selected_route_id: `${id}-${leg}`,
    display_name: null,
    side: "spbu_side",
    leg,
    leg_index: i,
    expected_distance_m: 500,
    expected_polyline: null,
  })),
});

const reading = (route: string, over: Partial<LatestLeg> = {}): LatestLeg => ({
  selected_route_id: route,
  site_id: route.split("-")[0],
  leg: route.split("-")[1],
  slot_time: "2026-10-07T07:30:00Z",
  duration_s: 60,
  delay_s: 10,
  congestion_index: null,
  speed_kmh: 40,
  baseline_samples: 30,
  ...over,
});

const a = mkSite("a", "Alpha", -6.2, 106.8);
const b = mkSite("b", "Bravo", -6.25, 106.75);
const c = mkSite("c", "Charlie", -5.1, 119.4);

describe("rankSites", () => {
  const latest = indexLatest([
    reading("a-approach", { speed_kmh: 40, delay_s: 5 }),
    reading("b-approach", { speed_kmh: 12, delay_s: 50 }), // jammed by speed
    reading("b-departure", { speed_kmh: 30, delay_s: 20 }),
  ]);

  it("puts the worst band first, then the larger delay, then name; no data last", () => {
    const ranked = rankSites([c, a, b], latest);
    expect(ranked.map((s) => s.site.site_id)).toEqual(["b", "a", "c"]);
    expect(ranked[0]).toMatchObject({ band: "jam", basis: "speed", worstLeg: "approach", worstDelay: 50 });
    expect(ranked[2]).toMatchObject({ band: "none", worstDelay: null });
  });

  it("is stable on ties by name", () => {
    const tie = indexLatest([reading("a-approach"), reading("b-approach")]);
    expect(rankSites([b, a], tie).map((s) => s.site.name)).toEqual(["Alpha", "Bravo"]);
  });

  it("summarises slowed sites, the worst one, the newest slot and the lowest baseline", () => {
    const s = summarize(rankSites([a, b, c], latest), latest);
    expect(s).toMatchObject({ total: 3, reporting: 2, slowed: 1, slotTime: "2026-10-07T07:30:00Z", baseline: 30 });
    expect(s.worst?.site.site_id).toBe("b");
  });

  it("names the head of the ranking as worst, even when another site has a larger delay", () => {
    // b: jam by speed (rank first) with a delay of 50 s; a: lighter band but 90 s.
    const mixed = indexLatest([
      reading("a-approach", { speed_kmh: 40, delay_s: 90 }),
      reading("b-approach", { speed_kmh: 12, delay_s: 50 }),
    ]);
    const ranked = rankSites([a, b], mixed);
    expect(summarize(ranked, mixed).worst).toBe(ranked.find((s) => s.worstDelay !== null));
    expect(summarize(ranked, mixed).worst?.site.site_id).toBe("b");
  });

  it("summarises an empty feed without a worst site or baseline", () => {
    const s = summarize(rankSites([a], new Map()), new Map());
    expect(s).toMatchObject({ reporting: 0, slowed: 0, worst: null, slotTime: null, baseline: null });
  });
});

describe("orderSites", () => {
  const latest = indexLatest([reading("a-approach", { speed_kmh: 40 }), reading("b-approach", { speed_kmh: 12 })]);
  const withCity = (s: Site, city: string): Site => ({ ...s, city });
  const ranked = rankSites([withCity(a, "Zeta"), withCity(b, "Beta"), withCity(c, "Beta")], latest); // b, a, c

  it("keeps the ranking for worst first and filters to slowed sites", () => {
    expect(orderSites(ranked, "worst", "all").map((s) => s.site.site_id)).toEqual(["b", "a", "c"]);
    expect(orderSites(ranked, "worst", "slowed").map((s) => s.site.site_id)).toEqual(["b"]);
  });
  it("sorts by name, or by city then name", () => {
    expect(orderSites(ranked, "name", "all").map((s) => s.site.name)).toEqual(["Alpha", "Bravo", "Charlie"]);
    expect(orderSites(ranked, "city", "all").map((s) => s.site.name)).toEqual(["Bravo", "Charlie", "Alpha"]);
  });
});

describe("baselineDaysLeft", () => {
  it("counts whole days at 48 readings a day", () => {
    expect(baselineDaysLeft(0)).toBe(7);
    expect(baselineDaysLeft(BASELINE_FULL - 1)).toBe(1);
    expect(baselineDaysLeft(BASELINE_FULL)).toBe(0);
  });
});

describe("clusterPoints", () => {
  const pts = [
    { id: "a", ...a.location },
    { id: "b", ...b.location },
    { id: "c", ...c.location },
  ];
  it("groups the two Jakarta sites at national zoom and keeps Makassar apart", () => {
    const groups = clusterPoints(pts, 5);
    expect(groups.map((g) => g.ids)).toEqual([["a", "b"], ["c"]]);
    expect(groups[0].lat).toBeCloseTo(-6.225);
  });
  it("merges groups whose marker boxes would still overlap after a first merge", () => {
    // Four points along a line, each ~70 px apart at zoom 7: pairwise neighbours overlap, so all four end up together
    // or in groups that no longer overlap each other.
    const line = [0, 1, 2, 3].map((k) => ({ id: `p${k}`, lat: -6.2, lng: 106.8 + k * 0.1 }));
    const groups = clusterPoints(line, 7);
    const px = (g: { lat: number; lng: number }) => (g.lng + 180) / 360 * 256 * 2 ** 7;
    for (let i = 0; i < groups.length; i++)
      for (let j = i + 1; j < groups.length; j++) expect(Math.abs(px(groups[i]) - px(groups[j]))).toBeGreaterThanOrEqual(96);
    expect(groups.flatMap((g) => g.ids).sort()).toEqual(["p0", "p1", "p2", "p3"]);
  });
  it("splits them once zoomed in", () => {
    expect(clusterPoints(pts, 12).map((g) => g.ids)).toEqual([["a"], ["b"], ["c"]]);
  });
});
