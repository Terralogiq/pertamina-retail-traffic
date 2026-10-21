import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PoiAnalysis, PoiSite, PoiStat, getPoiAnalysis } from "./analysisApi";
import {
  describe as describeStat,
  formatP,
  formatRho,
  logCount,
  pointsFor,
  ranks,
  siteLabel,
  sortSites,
  strength,
  unit,
} from "./analysisModel";
import { CaveatBanner, SiteTable, SmallMultiples, SummaryPlot, scatterOption } from "./PlacesVsTraffic";

const site = (id: string, city: string, delay: number | null, malls: (number | null)[] | null, road: "urban" | "toll" = "urban"): PoiSite => ({
  site_id: id,
  name: `SPBU ${id}`,
  city,
  road_class: road,
  metrics: { delay, peak: 2, busy: 0.25 },
  busy_hours: { approach: 3, departure: 3 },
  poi: malls && { shopping_mall: malls, gas_station: [0, 1, 2] },
});

const stat = (group: string, radius_m: number, rho: number | null, lo: number | null, hi: number | null, p: number | null): PoiStat => ({
  group,
  radius_m,
  rho,
  ci_low: lo,
  ci_high: hi,
  p,
  loo_min: rho == null ? null : rho - 0.1,
  loo_max: rho == null ? null : rho + 0.1,
  n: 10,
});

const analysis: PoiAnalysis = {
  metric: "delay",
  leg: "both",
  exclude_toll: false,
  ready: true,
  days: 15,
  ready_days: 7,
  window: { from: "2026-10-06T17:30:00Z", to: "2026-10-21T03:00:00Z" },
  places_run: "2026-10-18T19:00:09Z",
  groups: [
    { id: "gas_station", label: "Other fuel stations" },
    { id: "shopping_mall", label: "Shopping malls" },
  ],
  radii: [500, 1000, 3000],
  sites: [
    site("a", "Bandung", 135, [20, 63, 400]),
    site("b", "Surabaya", 10, [5, 18, 220]),
    site("c", "Karawang", 7, [0, 18, 240], "toll"),
  ],
  stats: [
    ...[500, 1000, 3000].map((r) => stat("gas_station", r, 0.31, -0.58, 0.89, 0.39)),
    stat("shopping_mall", 500, 0.65, -0.13, 1, 0.05),
    stat("shopping_mall", 1000, 0.66, 0.02, 0.93, 0.045),
    stat("shopping_mall", 3000, -0.02, -0.74, 0.66, 0.97),
  ],
};

afterEach(() => vi.unstubAllGlobals());

describe("places analysis client", () => {
  it("passes the switches as query parameters", async () => {
    const f = vi.fn(async () => Response.json(analysis));
    vi.stubGlobal("fetch", f);
    await getPoiAnalysis("busy", "approach", true);
    expect(f).toHaveBeenCalledWith("/api/places/analysis?metric=busy&leg=approach&exclude_toll=true", expect.anything());
  });
});

describe("places analysis model", () => {
  it("formats rho with a sign and a real minus, and p without false precision", () => {
    expect(formatRho(0.314)).toBe("+0.31");
    expect(formatRho(-0.58)).toBe("−0.58");
    expect(formatRho(-0.001)).toBe("+0.00");
    expect(formatRho(null)).toBe("n/a");
    expect(formatP(0.045)).toBe("0.045");
    expect(formatP(0.39)).toBe("0.39");
    expect(formatP(0.0004)).toBe("< 0.001");
  });

  it("strength words describe size only", () => {
    expect([0.1, -0.45, 0.8].map(strength)).toEqual(["weak", "moderate", "strong"]);
  });

  it("the sentence says no clear relationship when the interval spans zero, and never says significant", () => {
    expect(describeStat(stat("g", 500, 0.31, -0.58, 0.89, 0.39), 18)).toBe(
      "No clear relationship: ρ +0.31, compatible with −0.58 to +0.89.",
    );
    const clear = describeStat(stat("g", 500, 0.66, 0.02, 0.93, 0.045), 18);
    expect(clear).toContain("A strong positive pattern");
    expect(clear).toContain("About 1 of 18 such comparisons would look like this by chance; not corrected.");
    expect(clear.toLowerCase()).not.toContain("significant");
    expect(describeStat(stat("g", 500, null, null, null, null), 18)).toMatch(/Not enough variation/);
  });

  it("ranks give ties the average rank; counts are shifted by one for the log axis", () => {
    expect(ranks([10, 20, 20, 30])).toEqual([1, 2.5, 2.5, 4]);
    expect(logCount(0)).toBe(1);
    expect(unit(5, 0, 10)).toBe(0.5);
    expect(unit(5, 3, 3)).toBe(0.5);
  });

  it("a site joins a plot only with both a count and a traffic value; the toll site is labelled", () => {
    const sites = [site("a", "Bandung", 135, [20, 63, 400]), site("b", "Surabaya", null, [5, 18, 220]), site("c", "Karawang", 7, null, "toll")];
    expect(pointsFor(sites, "shopping_mall", 1, "delay").map((p) => p.site.site_id)).toEqual(["a"]);
    expect(siteLabel(sites[2])).toBe("Karawang (toll)");
  });

  it("adds the site id when two sites share a city, so labels and links never read alike", () => {
    const pair = [site("24.351.34", "Bandar Lampung", 27, [16, 52, 557]), site("24.351.97", "Bandar Lampung", 30, [7, 17, 150]), ...analysis.sites];
    expect(siteLabel(pair[0], pair)).toBe("Bandar Lampung 24.351.34");
    expect(siteLabel(pair[1], pair)).toBe("Bandar Lampung 24.351.97");
    expect(siteLabel(pair[2], pair)).toBe("Bandung");
    expect(siteLabel(pair[4], pair)).toBe("Karawang (toll)");
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <SiteTable data={{ ...analysis, sites: pair }} radiusIndex={1} hover={null} onHover={() => {}} />
      </MemoryRouter>,
    );
    expect(html).toContain(">Bandar Lampung 24.351.34</a>");
    expect(html).toContain(">Bandar Lampung 24.351.97</a>");
    const points = pointsFor(pair, "shopping_mall", 1, "delay");
    const option = scatterOption(points, "delay", false, null, pair) as { series: { data: { name: string }[] }[] };
    expect(option.series[0].data.slice(0, 2).map((d) => d.name)).toEqual(["Bandar Lampung 24.351.34", "Bandar Lampung 24.351.97"]);
  });

  it("sorts by a metric or a count with missing values last, either way", () => {
    const sites = analysis.sites.concat(site("d", "Medan", null, null));
    expect(sortSites(sites, "delay", true, 1).map((s) => s.site_id)).toEqual(["a", "b", "c", "d"]);
    expect(sortSites(sites, "delay", false, 1).map((s) => s.site_id)).toEqual(["c", "b", "a", "d"]);
    expect(sortSites(sites, "poi:shopping_mall", true, 2).map((s) => s.site_id)).toEqual(["a", "c", "b", "d"]);
    expect(sortSites(sites, "city", false, 0).map((s) => s.city)).toEqual(["Bandung", "Karawang", "Medan", "Surabaya"]);
  });
});

describe("caveat banner", () => {
  it("states the dated result of the correction without claiming a relationship is ruled out, in every state", () => {
    for (const html of [renderToStaticMarkup(<CaveatBanner />), renderToStaticMarkup(<CaveatBanner sites={10} days={15} tests={18} />)]) {
      expect(html).toContain("In the 14 October 2026 analysis, none of 47 POI measures showed a relationship that survived correction");
      expect(html).toContain("a relationship cannot be ruled out either");
      expect(html).not.toContain("no relationship holds up");
      expect(html).toContain("not causes");
    }
  });

  it("shows live counts once known", () => {
    expect(renderToStaticMarkup(<CaveatBanner />)).not.toContain("sites, ");
    const html = renderToStaticMarkup(<CaveatBanner sites={9} days={15} tests={18} />);
    expect(html).toContain("9 sites, 15 days.");
    expect(html).toContain("18 comparisons are shown; about 1 would look");
  });
});

describe("summary plot", () => {
  it("lists every group at every radius in the given order with rho, interval and p", () => {
    const html = renderToStaticMarkup(<SummaryPlot data={analysis} group="shopping_mall" radius={1000} onSelect={() => {}} />);
    expect(html.indexOf("Other fuel stations")).toBeLessThan(html.indexOf("Shopping malls"));
    expect((html.match(/class="poi-row( selected)?"/g) ?? []).length).toBe(6);
    expect(html).toContain("1 km: rho +0.66, interval +0.02 to +0.93, p 0.045");
    expect(html).toContain('class="poi-row selected"');
    expect(html).toContain("poi-mark circle");
    expect(html).toContain("poi-mark square");
    expect(html).toContain("poi-mark triangle");
  });

  it("uses no word that calls a row significant", () => {
    const html = renderToStaticMarkup(<SummaryPlot data={analysis} group="gas_station" radius={500} onSelect={() => {}} />);
    expect(html.toLowerCase()).not.toContain("significant");
  });
});

describe("scatter", () => {
  it("plots count + 1 on a log axis, labels each site and draws the toll site as a hollow diamond", () => {
    const points = pointsFor(analysis.sites, "shopping_mall", 0, "delay");
    const option = scatterOption(points, "delay", false, null, analysis.sites) as {
      xAxis: { type: string };
      series: { data: { value: number[]; name: string; symbol: string }[] }[];
    };
    expect(option.xAxis.type).toBe("log");
    const data = option.series[0].data;
    expect(data.map((d) => d.name)).toEqual(["Bandung", "Surabaya", "Karawang (toll)"]);
    expect(data.map((d) => d.value[0])).toEqual([21, 6, 1]); // counts 20, 5, 0 plus one
    expect(data.map((d) => d.symbol)).toEqual(["circle", "circle", "diamond"]);
  });

  it("shifts overlapping point labels apart instead of hiding them", () => {
    const points = pointsFor(analysis.sites, "shopping_mall", 0, "delay");
    const option = scatterOption(points, "delay", false, null, analysis.sites) as { series: { labelLayout: { moveOverlap: string; hideOverlap?: boolean } }[] };
    expect(option.series[0].labelLayout).toEqual({ moveOverlap: "shiftY" });
  });

  it("show ranks plots rank against rank on linear axes", () => {
    const points = pointsFor(analysis.sites, "shopping_mall", 0, "delay");
    const option = scatterOption(points, "delay", true, null, analysis.sites) as { xAxis: { type: string }; series: { data: { value: number[] }[] }[] };
    expect(option.xAxis.type).toBe("value");
    expect(option.series[0].data.map((d) => d.value)).toEqual([[3, 3], [2, 2], [1, 1]]);
  });
});

describe("small multiples and site table", () => {
  it("draws one panel per group and radius with rho in each, and outlines the selection", () => {
    const html = renderToStaticMarkup(
      <SmallMultiples data={analysis} group="shopping_mall" radius={3000} ranked={false} hover={null} onHover={() => {}} onSelect={() => {}} />,
    );
    expect((html.match(/class="poi-mini( selected)?"/g) ?? []).length).toBe(6);
    expect(html).toContain("poi-mini selected");
    expect(html).toContain("Shopping malls within 3 km: rho −0.02");
  });

  it("puts rho in a header above the plot, not over it", () => {
    const html = renderToStaticMarkup(
      <SmallMultiples data={analysis} group="shopping_mall" radius={3000} ranked={false} hover={null} onHover={() => {}} onSelect={() => {}} />,
    );
    expect(html.indexOf("poi-mini-rho")).toBeGreaterThan(-1);
    expect(html.indexOf("poi-mini-rho")).toBeLessThan(html.indexOf("poi-mini-svg"));
  });

  it("lists sites with links to their pages, counts at the selected radius and the toll site marked", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <SiteTable data={analysis} radiusIndex={1} hover="b" onHover={() => {}} />
      </MemoryRouter>,
    );
    expect(html).toContain('href="/site/a"');
    expect(html).toContain("Karawang (toll)");
    expect(html).toContain("within 1 km");
    expect(html).toContain("135 s/km");
    expect(html).toContain('<tr class="hot"');
  });
});
