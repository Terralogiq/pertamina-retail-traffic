import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Site } from "../map/api";
import type { QueueRiskResponse, QueueRiskSite, StationThemes, StationThemesResponse, Tier } from "./api";
import { StationData, StationTableView, loadStationData, stationApi } from "./StationTable";
import { StationSort, buildRows, sortRows, tierDetail, topComplaintText } from "./model";

// Ten stations in the plan's 2026-10-14 ranking (server order). Names sort differently from that order.
const STATIONS: [id: string, name: string, tier: Tier][] = [
  ["s1", "Pemogan", "strong"],
  ["s2", "MT Haryono", "moderate"],
  ["s3", "Makassar", "moderate"],
  ["s4", "Lingkar Selatan", "moderate"],
  ["s5", "Tirtayasa", "weak"],
  ["s6", "Antasari", "weak"],
  ["s7", "KM57A", "weak"],
  ["s8", "Gayungan", "none"],
  ["s9", "Daan Mogot", "cannot_tell"],
  ["s0", "Bandung", "cannot_tell"],
];

const site = (id: string, name: string): Site => ({
  site_id: id,
  name,
  place_id: "p",
  road_name: null,
  city: `City of ${name}`,
  road_type: null,
  road_class: "urban",
  timezone: "Asia/Jakarta",
  location: { lat: 0, lng: 0 },
  legs: [],
});

const SITES = STATIONS.map(([id, name]) => site(id, name));

const riskSite = (id: string, tier: Tier, over: Partial<QueueRiskSite> = {}): QueueRiskSite => ({
  site_id: id,
  tier,
  als_pct: 6,
  both_slow_pct: 8,
  departure_only_pct: 16,
  days_with_2h_als: 10,
  full_days: 14,
  als_median_delay_s: 90,
  confidence: { level: "low", reason: "Short observation window", as_of: "2026-10-14" },
  ...over,
});

const RISK: QueueRiskResponse = {
  window_days: 28,
  sites: STATIONS.map(([id, , tier]) => riskSite(id, tier)),
};

const themes = (id: string, queue: number, top: StationThemes["top"], n = 12): StationThemes => ({
  site_id: id,
  n_labelled: n,
  queue_complaints: queue,
  top,
  categories: [],
});

// Complaint counts: s1 5, s2 3, s3 3, s4 0, s5 1, s6 2, s7 0, s8 4, s9 0, s0 2. s2 and s3 tie on both counts.
const THEMES: StationThemesResponse = {
  sites: [
    themes("s1", 5, { categories: ["antrian"], count: 5 }),
    themes("s2", 3, { categories: ["antrian", "harga"], count: 3 }),
    themes("s3", 3, { categories: ["antrian"], count: 3 }),
    themes("s4", 0, null),
    themes("s5", 1, { categories: ["pelayanan_petugas"], count: 6 }),
    themes("s6", 2, { categories: ["harga"], count: 2 }),
    themes("s7", 0, null, 0),
    themes("s8", 4, { categories: ["antrian"], count: 4 }),
    themes("s9", 0, { categories: ["toilet"], count: 1 }),
    themes("s0", 2, { categories: ["kebersihan"], count: 2 }),
  ],
};

const OK: StationData = { risk: RISK, themes: THEMES };

const render = (data: StationData, sort: StationSort = "name", sites: Site[] | null = SITES) =>
  renderToStaticMarkup(
    <MemoryRouter>
      <StationTableView sites={sites} data={data} sort={sort} onSort={() => {}} />
    </MemoryRouter>,
  );

/** Visible text with tags removed and entities for the apostrophe decoded. */
const textOf = (html: string) =>
  html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ");

const order = (html: string) => [...html.matchAll(/href="\/site\/([^"]+)"/g)].map((m) => m[1]);
const nameOrder = (html: string) =>
  order(html).map((id) => STATIONS.find(([sid]) => sid === id)![1]);

describe("StationTable", () => {
  it("renders one row per site, each linking to its site page", () => {
    const html = render(OK);
    expect(html.match(/<tbody>[\s\S]*<\/tbody>/)![0].split("<tr>").length - 1).toBe(10);
    expect(order(html)).toHaveLength(10);
    expect(html).toContain('href="/site/s1"');
    expect(textOf(html)).toContain("Stations at a glance");
    expect(textOf(html)).toContain("City of Pemogan");
  });

  it("sorts by name by default", () => {
    expect(nameOrder(render(OK))).toEqual([
      "Antasari",
      "Bandung",
      "Daan Mogot",
      "Gayungan",
      "KM57A",
      "Lingkar Selatan",
      "Makassar",
      "MT Haryono",
      "Pemogan",
      "Tirtayasa",
    ]);
  });

  it("sets aria-sort on the active column header only", () => {
    const sortedHeaders = (sort: StationSort) =>
      [...render(OK, sort).matchAll(/<th scope="col"[^>]*aria-sort="(\w+)"[^>]*>\s*([^<]*?)\s*</g)].map((m) => [m[2], m[1]]);
    expect(sortedHeaders("name")).toEqual([["Station", "ascending"]]);
    expect(sortedHeaders("risk")).toEqual([["Slower before than after", "other"]]);
    expect(sortedHeaders("complaints")).toEqual([["Queue complaints", "descending"]]);
    expect(sortedHeaders("top")).toEqual([["Top complaint", "descending"]]);
  });

  it("queue-risk sort follows the server order and puts cannot tell last", () => {
    const names = nameOrder(render(OK, "risk"));
    expect(names).toEqual(STATIONS.map(([, n]) => n));
    expect(names.slice(-2)).toEqual(["Daan Mogot", "Bandung"]);
  });

  it("queue-risk sort moves cannot tell last even when the server lists it earlier", () => {
    const [first, ...rest] = RISK.sites;
    const shuffled = { ...RISK, sites: [riskSite("s9", "cannot_tell"), first, ...rest.filter((r) => r.site_id !== "s9")] };
    const names = nameOrder(render({ risk: shuffled, themes: THEMES }, "risk"));
    expect(names[0]).toBe("Pemogan");
    expect(names.slice(-2).sort()).toEqual(["Bandung", "Daan Mogot"]);
  });

  it("sorts by queue complaints, most first, ties by name", () => {
    expect(nameOrder(render(OK, "complaints"))).toEqual([
      "Pemogan", // 5
      "Gayungan", // 4
      "Makassar", // 3 (ties by name)
      "MT Haryono", // 3
      "Antasari", // 2
      "Bandung", // 2
      "Tirtayasa", // 1
      "Daan Mogot", // 0
      "KM57A",
      "Lingkar Selatan",
    ]);
  });

  it("sorts by top complaint count, most first, ties by name; no top counts as 0", () => {
    expect(nameOrder(render(OK, "top"))).toEqual([
      "Tirtayasa", // 6
      "Pemogan", // 5
      "Gayungan", // 4
      "Makassar", // 3
      "MT Haryono", // 3
      "Antasari", // 2
      "Bandung", // 2
      "Daan Mogot", // 1
      "KM57A", // none
      "Lingkar Selatan", // none
    ]);
  });

  it("lists every tied top complaint in English with the shared count", () => {
    const text = textOf(render(OK));
    expect(text).toContain("Queues, Price (3 each)");
    expect(text).toContain("Staff service (6)");
    expect(text).not.toContain("antrian");
    expect(text).not.toContain("pelayanan_petugas");
    expect(topComplaintText(null)).toBeNull();
  });

  it("shows a dash for a station with no complaint", () => {
    const rows = sortRows(buildRows(SITES, RISK.sites, THEMES.sites), "name");
    const lingkar = rows.find((r) => r.site.site_id === "s4")!;
    expect(topComplaintText(lingkar.themes!.top)).toBeNull();
    const html = render({ risk: RISK, themes: { sites: [THEMES.sites[3]] } }, "name", [SITES[3]]);
    expect(html).toMatch(/<td>—<\/td>/);
  });

  it("explains a cannot-tell station instead of giving days", () => {
    const html = render({ risk: { ...RISK, sites: [riskSite("s9", "cannot_tell")] }, themes: THEMES }, "name", [SITES[8]]);
    const text = textOf(html);
    expect(text).toContain("Cannot tell");
    expect(text).toContain("Road past the station is as slow, so this can't be seen");
    expect(text).not.toContain("of 14 days");
  });

  it("gives tier, days and usual delay for a tier with a signal, and only the tier for none", () => {
    expect(tierDetail(riskSite("a", "strong", { days_with_2h_als: 12, full_days: 14, als_median_delay_s: 90 }))).toBe(
      "on 12 of 14 days, usually +1.5 min",
    );
    expect(tierDetail(riskSite("a", "weak", { days_with_2h_als: 2, full_days: 14, als_median_delay_s: 45 }))).toBe(
      "on 2 of 14 days, usually +45 s",
    );
    expect(tierDetail(riskSite("a", "weak", { als_median_delay_s: null }))).toBe("on 10 of 14 days");
    expect(tierDetail(riskSite("a", "none"))).toBe("");
    const text = textOf(render(OK));
    expect(text).toContain("Strong");
    expect(text).toContain("on 10 of 14 days, usually +1.5 min");
  });

  it("shows the confidence level with its reason and as-of date as visible text; a dash when missing", () => {
    const text = textOf(render(OK));
    expect(text).toContain("Low");
    expect(text).toContain("Short observation window");
    expect(text).toContain("as of 2026-10-14");
    const none = render(
      { risk: { ...RISK, sites: [riskSite("s1", "strong", { confidence: null })] }, themes: THEMES },
      "name",
      [SITES[0]],
    );
    expect(textOf(none)).not.toContain("as of");
    expect(none).toMatch(/<td>—<\/td>/);
  });

  it("labels the traffic column without the word queue; Queue complaints keeps it", () => {
    const html = render(OK);
    const header = textOf(html.match(/<thead>[\s\S]*<\/thead>/)![0]);
    expect(header).toContain("Slower before than after");
    expect(header).toContain("Queue complaints");
    expect(header).toContain("Reviews labelled");
    expect(header.replace("Queue complaints", "")).not.toMatch(/queue/i);
    const traffic = textOf(html).replace(/Queue complaints|Queues/g, "");
    expect(traffic).not.toMatch(/queue/i);
  });

  it("captions state the window from the response", () => {
    const text = textOf(render({ risk: { ...RISK, window_days: 14 }, themes: THEMES }));
    expect(text).toContain(
      "Road traffic on the 500 m before and after each station, from the last 14 days. Not a count of cars at the pumps, and not checked on the ground.",
    );
    expect(text).toContain(
      "Complaints come from a sample of at most 15 Google reviews per window and station. Counts, not rates.",
    );
  });

  it("still renders every row when the queue-risk endpoint fails, with dashes and a notice", () => {
    const html = render({ risk: new Error("The server had a problem (HTTP 500)."), themes: THEMES });
    expect(order(html)).toHaveLength(10);
    expect(html).toContain('role="alert"');
    expect(textOf(html)).toContain("HTTP 500");
    expect(textOf(html)).not.toContain("Strong");
    expect(textOf(html)).toContain("Queues (5)"); // the review columns are intact
    expect(textOf(html)).not.toContain("from the last"); // no window to state
  });

  it("still renders every row when the review-themes endpoint fails, with dashes and a notice", () => {
    const html = render({ risk: RISK, themes: new Error("No connection") });
    expect(order(html)).toHaveLength(10);
    expect(html).toContain('role="alert"');
    expect(textOf(html)).toContain("No connection");
    expect(textOf(html)).toContain("Strong");
    expect(textOf(html)).toContain("from the last 28 days");
    expect(textOf(html)).not.toContain("Queues (5)");
  });

  it("shows a skeleton while loading and no rows", () => {
    for (const data of [{ risk: undefined, themes: THEMES }, { risk: RISK, themes: undefined }] as StationData[]) {
      const html = render(data);
      expect(html).toContain('aria-label="Loading stations"');
      expect(order(html)).toHaveLength(0);
    }
    expect(render(OK, "name", null)).toContain('aria-label="Loading stations"');
  });

  it("carries no demo-only badge", () => {
    expect(render(OK).toLowerCase()).not.toContain("demo");
  });

  it("has the sort control with the four orders, the current one pressed", () => {
    const html = render(OK, "complaints");
    for (const label of ["Name", "Slower before than after", "Queue complaints", "Top complaint count"]) expect(html).toContain(label);
    expect(html).toMatch(/segment selected"[^>]*aria-pressed="true">Queue complaints/);
  });
});

describe("loadStationData", () => {
  const collect = () => {
    const got: Partial<StationData> = {};
    const set = (key: keyof StationData) => (v: unknown) => void ((got as Record<string, unknown>)[key] = v);
    return { got, set: set as Parameters<typeof loadStationData>[0] };
  };

  it("reports each endpoint on its own, so one failure leaves the other's data", async () => {
    const api = {
      getQueueRisk: vi.fn(() => Promise.reject(new Error("boom"))),
      getStationThemes: vi.fn(() => Promise.resolve(THEMES)),
    } satisfies typeof stationApi;
    const { got, set } = collect();
    await loadStationData(set, api);
    expect(got.risk).toBeInstanceOf(Error);
    expect((got.risk as Error).message).toBe("boom");
    expect(got.themes).toBe(THEMES);
    expect(api.getQueueRisk).toHaveBeenCalledTimes(1);
    expect(api.getStationThemes).toHaveBeenCalledTimes(1);
  });

  it("passes both responses through when both succeed", async () => {
    const api = {
      getQueueRisk: vi.fn(() => Promise.resolve(RISK)),
      getStationThemes: vi.fn(() => Promise.resolve(THEMES)),
    } satisfies typeof stationApi;
    const { got, set } = collect();
    await loadStationData(set, api);
    expect(got).toEqual({ risk: RISK, themes: THEMES });
  });
});
