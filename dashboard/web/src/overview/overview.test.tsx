import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { LatestLeg, Site } from "../map/api";
import { BASELINE_FULL, indexLatest } from "../map/bands";
import { QueueLegend } from "../map/Legend";
import { QueueMarker } from "../map/MapMarker";
import { OverviewView, OverviewViewProps } from "../map/Overview";
import { rankSites, siteState } from "../map/severity";
import type { WeatherLatest } from "../weather/api";
import type { QueueRiskResponse, QueueRiskSite, StationThemes, StationThemesResponse, Tier } from "./api";
import {
  CANNOT_TELL_TEXT,
  QueueRisk,
  RISK_GUIDANCE,
  RISK_LABELS,
  RISK_LEVEL,
  RISK_MARKER_TEXT,
  RISK_ORDER,
  StationRow,
  buildRows,
  effectiveMode,
  orderByRank,
  orderByRisk,
  reviewLine,
  reviewSignal,
  riskOf,
  riskSummary,
  selectionReducer,
  trafficLine,
  trafficSignal,
} from "./model";
import { SiteWeatherCell, StationList, StationListRow, TrafficRow } from "./StationList";
import { StationData, loadStationData, stationApi } from "./useStationData";

// The 2026-10-21 data behind the plan's risk table, in the server's queue-risk order (tier, days, delay; cannot tell last).
const STATIONS: [id: string, name: string, tier: Tier, roadQueue: number][] = [
  ["54.801.17", "Pemogan", "moderate", 2],
  ["61.761.03", "MT Haryono", "moderate", 0],
  ["74.902.22", "Makassar", "moderate", 0],
  ["34.121.03", "Lingkar Selatan", "moderate", 0],
  ["24.351.97", "Tirtayasa", "weak", 1],
  ["KM57A", "KM57A", "weak", 0],
  ["54.601.80", "Gayungan", "none", 2],
  ["34.117.12", "Daan Mogot", "cannot_tell", 1],
  ["24.351.34", "Antasari", "cannot_tell", 0],
  ["34.401.16", "Bandung", "cannot_tell", 0],
];

const nameOf = (id: string) => STATIONS.find(([sid]) => sid === id)![1];

const site = (id: string, name: string, lng: number): Site => ({
  site_id: id,
  name,
  place_id: "p",
  road_name: null,
  city: `City of ${name}`,
  road_type: null,
  road_class: "urban",
  timezone: "Asia/Jakarta",
  location: { lat: -6, lng },
  legs: [
    { selected_route_id: `${id}-a`, display_name: null, side: null, leg: "approach", leg_index: 0, expected_distance_m: 500, expected_polyline: null },
    { selected_route_id: `${id}-d`, display_name: null, side: null, leg: "departure", leg_index: 1, expected_distance_m: 500, expected_polyline: null },
  ],
});

const SITES = STATIONS.map(([id, name], i) => site(id, name, 100 + i));

const riskSite = (id: string, tier: Tier, over: Partial<QueueRiskSite> = {}): QueueRiskSite => ({
  site_id: id,
  tier,
  als_pct: 6,
  both_slow_pct: 8,
  departure_only_pct: 16,
  days_with_2h_als: tier === "strong" || tier === "moderate" ? 8 : tier === "weak" ? 2 : 0,
  full_days: 8,
  als_median_delay_s: 90,
  confidence: { level: "low", reason: "Short observation window", as_of: "2026-10-14" },
  ...over,
});

const RISK: QueueRiskResponse = { window_days: 28, sites: STATIONS.map(([id, , tier]) => riskSite(id, tier)) };

const themes = (id: string, roadQueue: number, over: Partial<StationThemes> = {}): StationThemes => ({
  site_id: id,
  n_labelled: 12,
  queue_complaints: 5,
  top: { categories: ["antrian"], count: 4 },
  categories: [],
  queue_recent: 3,
  road_queue_recent: roadQueue,
  ...over,
});

const THEMES: StationThemesResponse = { sites: STATIONS.map(([id, , , rq]) => themes(id, rq)) };

const ROWS = buildRows(SITES, RISK.sites, THEMES.sites);
const rowOf = (rows: StationRow[], id: string) => rows.find((r) => r.site.site_id === id)!;

/** Visible text with tags removed and the apostrophe entity decoded. */
const textOf = (html: string) =>
  html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/\s+/g, " ");

const html = (node: ReactElement) => renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);
const rowOrder = (markup: string) => [...markup.matchAll(/data-site-id="([^"]+)"/g)].map((m) => nameOf(m[1]));

describe("risk levels on the 2026-10-21 numbers", () => {
  const expected: Record<string, QueueRisk> = {
    Pemogan: "both",
    "MT Haryono": "traffic",
    Makassar: "traffic",
    "Lingkar Selatan": "traffic",
    Gayungan: "reviews",
    Tirtayasa: "reviews",
    "Daan Mogot": "reviews",
    Antasari: "busy",
    Bandung: "busy",
    KM57A: "low",
  };

  it("puts each station at the plan's level", () => {
    expect(Object.fromEntries(ROWS.map((r) => [r.site.name, r.queueRisk]))).toEqual(expected);
    const levels = (level: string) => ROWS.filter((r) => RISK_LEVEL[r.queueRisk] === level).map((r) => r.site.name).sort();
    expect(levels("red")).toEqual(["Daan Mogot", "Gayungan", "Lingkar Selatan", "MT Haryono", "Makassar", "Pemogan", "Tirtayasa"]);
    expect(levels("yellow")).toEqual(["Antasari", "Bandung"]);
    expect(levels("green")).toEqual(["KM57A"]);
  });

  it("flags cannot tell without counting it as a traffic signal", () => {
    expect(ROWS.filter((r) => r.cannotTell).map((r) => r.site.name)).toEqual(["Daan Mogot", "Antasari", "Bandung"]);
    expect(rowOf(ROWS, "34.117.12").traffic).toBe("no");
  });

  it("counts strong and moderate only; one road-queue review is enough", () => {
    for (const tier of ["strong", "moderate"] as Tier[]) expect(trafficSignal(riskSite("x", tier))).toBe("yes");
    for (const tier of ["weak", "none", "cannot_tell"] as Tier[]) expect(trafficSignal(riskSite("x", tier))).toBe("no");
    expect(reviewSignal(themes("x", 1))).toBe("yes");
    expect(reviewSignal(themes("x", 0))).toBe("no");
  });

  it("reports a missing entry as unknown, never as no", () => {
    expect(trafficSignal(undefined)).toBe("unknown");
    expect(reviewSignal(undefined)).toBe("unknown");
    const rows = buildRows(SITES, RISK.sites.slice(1), THEMES.sites.slice(1));
    expect(rowOf(rows, "54.801.17")).toMatchObject({ traffic: "unknown", reviews: "unknown", queueRisk: "low" });
  });

  it("rates from traffic alone when reviews failed, and marks reviews unavailable", () => {
    const rows = buildRows(SITES, RISK.sites, null);
    expect(rows.every((r) => r.reviews === "unknown")).toBe(true);
    expect(rowOf(rows, "54.801.17").queueRisk).toBe("traffic");
    expect(rowOf(rows, "54.601.80").queueRisk).toBe("low");
    expect(rowOf(rows, "34.117.12").queueRisk).toBe("busy"); // an unknown review signal counts as absent
    expect(reviewLine(undefined)).toBe("Reviews unavailable");
  });

  it("riskOf covers every combination; a review wins over cannot tell", () => {
    expect(riskOf("yes", "yes", false)).toBe("both");
    expect(riskOf("yes", "no", false)).toBe("traffic");
    expect(riskOf("yes", "unknown", false)).toBe("traffic");
    expect(riskOf("no", "yes", false)).toBe("reviews");
    expect(riskOf("unknown", "yes", false)).toBe("reviews");
    expect(riskOf("no", "yes", true)).toBe("reviews");
    expect(riskOf("no", "no", true)).toBe("busy");
    expect(riskOf("no", "unknown", true)).toBe("busy");
    expect(riskOf("no", "no", false)).toBe("low");
    expect(riskOf("unknown", "unknown", false)).toBe("low");
  });

  it("desk-check confidence never changes the level", () => {
    const rows = (level: "medium" | "very_low" | "none") =>
      buildRows(SITES, RISK.sites.map((r) => ({ ...r, confidence: { level, reason: "x", as_of: "2026-10-14" } })), THEMES.sites);
    const levels = (rs: StationRow[]) => rs.map((r) => r.queueRisk);
    expect(levels(rows("medium"))).toEqual(levels(ROWS));
    expect(levels(rows("very_low"))).toEqual(levels(ROWS));
    expect(levels(rows("none"))).toEqual(levels(ROWS));
  });

  it("labels say which signal, and the map pills stay short", () => {
    expect(RISK_LABELS).toEqual({
      both: "Queue risk: traffic + reviews",
      traffic: "Queue risk: traffic",
      reviews: "Queue risk: reviews",
      busy: "Busy road",
      low: "Low queue risk",
    });
    for (const text of Object.values(RISK_MARKER_TEXT)) expect(text.length).toBeLessThanOrEqual(9);
  });
});

describe("order", () => {
  it("queue risk: red (both, traffic, reviews), yellow, green; within a level the server's queue-risk order", () => {
    expect(orderByRisk(ROWS).map((r) => r.site.name)).toEqual([
      "Pemogan",
      "MT Haryono",
      "Makassar",
      "Lingkar Selatan",
      "Tirtayasa",
      "Gayungan",
      "Daan Mogot",
      "Antasari",
      "Bandung",
      "KM57A",
    ]);
  });

  it("puts a station without a queue-risk entry last in its group", () => {
    const rows = buildRows(SITES, RISK.sites.filter((r) => r.site_id !== "24.351.34"), THEMES.sites);
    expect(orderByRisk(rows).slice(-2).map((r) => r.site.name)).toEqual(["KM57A", "Antasari"]);
  });

  it("traffic now: worst first, as the live ranking", () => {
    const latest = indexLatest([
      reading("34.401.16-a", { congestion_index: 3.5, delay_s: 50 }), // jammed
      reading("KM57A-a", { congestion_index: 1.6, delay_s: 25 }),
    ]);
    const ranked = rankSites(SITES, latest);
    const names = orderByRank(ROWS, ranked).map((r) => r.site.name);
    expect(names.slice(0, 2)).toEqual(["Bandung", "KM57A"]);
    expect(names).toHaveLength(10);
  });
});

describe("summary line", () => {
  it("counts the three levels", () => {
    expect(riskSummary(ROWS)).toBe("7 queue risk · 2 busy road · 1 low");
  });
  it("drops empty levels", () => {
    const two = buildRows(SITES.slice(0, 2), [riskSite(SITES[0].site_id, "strong"), riskSite(SITES[1].site_id, "strong")], [
      themes(SITES[0].site_id, 1),
      themes(SITES[1].site_id, 1),
    ]);
    expect(riskSummary(two)).toBe("2 queue risk");
    expect(riskSummary(ROWS.filter((r) => r.queueRisk === "low"))).toBe("1 low");
  });
  it("has a fallback for no stations", () => {
    expect(riskSummary([])).toBe("No stations");
  });
});

describe("row wording", () => {
  it("traffic lines never say queue", () => {
    for (const tier of ["strong", "moderate", "weak", "none", "cannot_tell"] as Tier[]) {
      expect(trafficLine(riskSite("x", tier))).not.toMatch(/queue/i);
    }
    expect(trafficLine(undefined)).not.toMatch(/queue/i);
  });
  it("gives days for every tier with days, and the reason for cannot tell", () => {
    expect(trafficLine(riskSite("x", "strong"))).toBe("Slower before than after on 8 of 8 days");
    expect(trafficLine(riskSite("x", "weak"))).toBe("Slower before than after on only 2 of 8 days");
    expect(trafficLine(riskSite("x", "none"))).toBe("Not slower before than after on any of 8 days");
    expect(trafficLine(riskSite("x", "cannot_tell"))).toBe("Traffic can't tell here: both sides of the station are slow together");
    expect(trafficLine(undefined)).toBe("Slowdown comparison unavailable");
  });
  it("review line: count with plural, none, or unavailable", () => {
    expect(reviewLine(themes("x", 1))).toBe("1 review: queue reaches the road");
    expect(reviewLine(themes("x", 2))).toBe("2 reviews: queue reaches the road");
    expect(reviewLine(themes("x", 0))).toBe("No review says the queue reaches the road");
  });
});

const reading = (route: string, over: Partial<LatestLeg> = {}): LatestLeg => ({
  selected_route_id: route,
  site_id: route.split("-")[0],
  leg: route.endsWith("-a") ? "approach" : "departure",
  slot_time: "2026-10-15T07:30:00Z",
  duration_s: 45,
  delay_s: 5,
  congestion_index: 1,
  speed_kmh: 40,
  baseline_samples: BASELINE_FULL,
  ...over,
});

const renderRow = (row: StationRow, selected = false, showRisk = true, latest = new Map<string, LatestLeg>()) =>
  html(<StationListRow row={row} latest={latest} weather={undefined} selected={selected} showRisk={showRisk} onToggle={() => {}} />);

describe("station row", () => {
  const pemogan = rowOf(ROWS, "54.801.17");

  it("shows name, city, risk chip, both signal lines, complaints, top complaint and the live approach", () => {
    const latest = indexLatest([reading("54.801.17-a", { delay_s: 72 })]);
    const text = textOf(renderRow(pemogan, false, true, latest));
    for (const part of [
      "Pemogan",
      "City of Pemogan",
      "Queue risk: traffic + reviews",
      "Slower before than after on 8 of 8 days",
      "2 reviews: queue reaches the road",
      "Queue complaints: 3 in the last 12 months",
      "Top complaint: Queues (4)",
      "Approach now",
      "+1.2 min",
    ])
      expect(text).toContain(part);
    expect(text).not.toContain("antrian");
  });

  it("explains cannot tell (Daan Mogot) in place of days", () => {
    const text = textOf(renderRow(rowOf(ROWS, "34.117.12")));
    expect(text).toContain(CANNOT_TELL_TEXT);
    expect(text).toContain("Queue risk: reviews");
    expect(text).not.toContain("of 8 days");
  });

  it("says reviews are unavailable when review themes failed, and drops the complaint lines", () => {
    const row = rowOf(buildRows(SITES, RISK.sites, null), "54.801.17");
    const text = textOf(renderRow(row));
    expect(text).toContain("Reviews unavailable");
    expect(text).toContain("Queue risk: traffic");
    expect(text).not.toContain("Queue complaints");
    expect(text).not.toContain("Top complaint");
  });

  it("is a collapsed toggle button until selected; the details stay hidden", () => {
    const out = renderRow(pemogan);
    expect(out).toMatch(/<button type="button" class="station-row-button" aria-expanded="false" aria-controls="station-details-54.801.17"/);
    expect(out).toMatch(/<div class="station-details" id="station-details-54.801.17" hidden="">/);
  });

  it("when selected, expands to confidence with reason and date, review counts and a real link to the station", () => {
    const out = renderRow(pemogan, true);
    expect(out).toContain('aria-expanded="true"');
    expect(out).toContain("data-selected");
    expect(out).not.toMatch(/station-details[^>]*hidden/);
    const text = textOf(out);
    expect(text).toContain("Low. Short observation window. As of 2026-10-14");
    expect(text).toContain("Road-queue reviews, last 12 months 2");
    expect(text).toContain("Queue complaints, all sampled reviews 5");
    expect(text).toContain("Reviews labelled 12");
    expect(out).toMatch(/<a class="station-open" href="\/site\/54.801.17"[^>]*>Open station<\/a>/);
    // The link is outside the toggle button.
    expect(out.indexOf("</button>")).toBeLessThan(out.indexOf("Open station"));
  });

  it("has an always-visible Open link to the station page, a sibling after the toggle button (a click cannot toggle the row)", () => {
    for (const selected of [false, true]) {
      const out = renderRow(pemogan, selected);
      const link = out.match(/<a class="station-row-open" aria-label="Open Pemogan" href="\/site\/54\.801\.17"[^>]*>Open \u2192<\/a>/);
      expect(link, `selected=${selected}`).not.toBeNull();
      // Not inside the toggle button: the button closes first, and holds no link.
      expect(out.indexOf("</button>")).toBeLessThan(link!.index!);
      expect(out.slice(0, out.indexOf("</button>"))).not.toContain("<a ");
    }
    // Hidden details do not hide it.
    expect(renderRow(pemogan)).toMatch(/<div class="station-details"[^>]*hidden=""/);
  });

  it("encodes the site id in the Open link", () => {
    const odd: StationRow = { ...pemogan, site: { ...pemogan.site, site_id: "a/b c" } };
    expect(renderRow(odd)).toContain('class="station-row-open" aria-label="Open Pemogan" href="/site/a%2Fb%20c"');
  });

  it("hides the chip when no level can be given", () => {
    expect(textOf(renderRow(pemogan, false, false))).not.toContain("Queue risk");
  });

  it("shows a busy road and a low-risk station with the signal lines", () => {
    const busy = textOf(renderRow(rowOf(ROWS, "34.401.16")));
    expect(busy).toContain("Busy road");
    expect(busy).toContain(CANNOT_TELL_TEXT);
    const low = textOf(renderRow(rowOf(ROWS, "KM57A")));
    expect(low).toContain("Low queue risk");
    expect(low).toContain("Slower before than after on only 2 of 8 days");
  });
});

describe("traffic now row", () => {
  const pemogan = rowOf(ROWS, "54.801.17");
  const QUEUE_TEXT = ["Queue risk", "queue", "Queue complaints", "Top complaint", "reviews", "Slower before", "Confidence", "demo-only"];
  const renderNow = (id: string, latest: Map<string, LatestLeg>, weather?: WeatherLatest, selected = false) =>
    html(
      <TrafficRow
        state={siteState(rowOf(ROWS, id).site, latest)}
        latest={latest}
        weather={weather}
        selected={selected}
        onToggle={() => {}}
      />,
    );

  it("shows name, city, the worse leg's band, and both legs with delay, times usual and speed", () => {
    const latest = indexLatest([
      reading("54.801.17-a", { delay_s: 35, congestion_index: 1.6, speed_kmh: 28.4 }),
      reading("54.801.17-d", { delay_s: 114, congestion_index: 2.1, speed_kmh: 19.6 }),
    ]);
    const out = renderNow("54.801.17", latest);
    const text = textOf(out);
    expect(text).toContain("Pemogan");
    expect(text).toContain("City of Pemogan");
    expect(out).toContain('class="band-chip" data-band="heavy"');
    expect(text).toContain("Approach Moderate +35 s 1.6× 28 km/h");
    expect(text).toContain("Departure Heavy +1.9 min 2.1× 20 km/h");
    expect(text).toContain("Open station");
    expect(out).toContain('class="station-row-open" aria-label="Open Pemogan" href="/site/54.801.17"');
    expect(out.indexOf("</button>")).toBeLessThan(out.indexOf("station-row-open"));
  });

  it("shows a dash for a missing delay, congestion index or speed, and No data without a reading", () => {
    const latest = indexLatest([reading("54.801.17-a", { delay_s: null, congestion_index: null, speed_kmh: null })]);
    const text = textOf(renderNow("54.801.17", latest));
    expect(text).toContain("Approach No data \u2014 \u2014 \u2014");
    expect(text).toContain("Departure No data \u2014 \u2014 \u2014");
  });

  it("bands a leg without a full baseline on provisional speed, as the map pill does", () => {
    // 500 m in 100 s is 18 km/h against the 45 km/h urban usual: 2.5x and 55 s late, so Heavy, though the API has no index yet.
    const latest = indexLatest([
      reading("54.801.17-a", { baseline_samples: 10, duration_s: 100, delay_s: null, congestion_index: null, speed_kmh: 18 }),
    ]);
    const out = renderNow("54.801.17", latest);
    expect(out).toContain('class="band-chip" data-band="heavy"');
    expect(textOf(out)).toContain("Approach Heavy \u2014 \u2014 18 km/h");
  });

  it("has no queue-risk text, and the weather cell keeps its demo-only handling", () => {
    const latest = indexLatest([reading("54.801.17-a", { delay_s: 72 })]);
    const plain = textOf(renderNow("54.801.17", latest, { temperature_c: 31.4, demo_icon_uri: null } as WeatherLatest));
    for (const gone of QUEUE_TEXT) expect(plain).not.toContain(gone);
    expect(plain).toContain("31 \u00b0C");
    const withIcon = renderNow("54.801.17", latest, {
      temperature_c: 31.4,
      demo_icon_uri: "https://x/i",
      demo_condition_text: "Sunny",
    } as WeatherLatest);
    expect(withIcon).toContain("site-weather-icon");
    expect(withIcon).toContain("demo");
  });

  it("the list in traffic-now mode keeps the worst-first order and shows only traffic rows", () => {
    const latest = indexLatest([reading("34.401.16-a", { congestion_index: 3.5, delay_s: 50 })]);
    const ranked = rankSites(SITES, latest);
    const out = html(
      <StationList
        rows={orderByRank(ROWS, ranked)}
        latest={latest}
        weatherBySite={new Map()}
        heading="Stations, worst traffic first"
        mode="now"
        selectedId={null}
        showRisk
        windowDays={28}
        onToggle={() => {}}
      />,
    );
    expect(rowOrder(out)[0]).toBe("Bandung");
    expect(out).not.toContain("queue-chip");
    expect(out.match(/class="station-line station-leg"/g)).toHaveLength(20);
    const text = textOf(out);
    for (const gone of QUEUE_TEXT.filter((t) => t !== "demo-only")) expect(text).not.toContain(gone);
    expect(text).toContain("Stations, worst traffic first");
  });

  it("queue risk rows are unchanged: chip, signal lines, complaints, top complaint, no leg lines", () => {
    const text = textOf(renderRow(pemogan, false, true, indexLatest([reading("54.801.17-a", { delay_s: 72 })])));
    for (const part of ["Queue risk: traffic + reviews", "Slower before than after on 8 of 8 days", "Queue complaints: 3 in the last 12 months", "Top complaint: Queues (4)", "Approach now", "+1.2 min"])
      expect(text).toContain(part);
    expect(renderRow(pemogan)).not.toContain("station-leg");
    expect(renderRow(pemogan)).not.toContain("band-chip");
  });
});

describe("station list", () => {
  const list = (rows: StationRow[] | null) =>
    html(
      <StationList
        rows={rows}
        latest={new Map()}
        weatherBySite={new Map()}
        heading="Stations"
        mode="risk"
        selectedId={null}
        showRisk
        windowDays={28}
        onToggle={() => {}}
      />,
    );

  it("shows skeleton rows while loading", () => {
    const out = list(null);
    expect(out).toContain('role="status" aria-label="Loading stations"');
    expect(out.match(/class="skeleton"/g)).toHaveLength(4);
    expect(out).not.toContain("data-site-id");
  });

  it("lists every row and states the window", () => {
    const out = list(orderByRisk(ROWS));
    expect(rowOrder(out)).toHaveLength(10);
    expect(textOf(out)).toContain("last 28 days; not a count of cars");
  });
});

const props = (over: Partial<OverviewViewProps> = {}): OverviewViewProps => ({
  sites: SITES,
  latest: new Map(),
  weatherBySite: new Map(),
  error: "",
  station: { risk: RISK, themes: THEMES },
  mode: "risk",
  onMode: () => {},
  selected: null,
  dispatch: () => {},
  ...over,
});

describe("overview page", () => {
  it("opens on queue risk: summary, guidance line, toggle, level order", () => {
    const out = html(<OverviewView {...props()} />);
    const text = textOf(out);
    expect(text).toContain("7 queue risk · 2 busy road · 1 low");
    expect(text).toContain(RISK_GUIDANCE);
    expect(text).not.toContain("sites slowed");
    expect(out).toMatch(/segment selected"[^>]*aria-pressed="true">Queue risk/);
    expect(text).toContain("Traffic now");
    expect(text).toContain("Stations, highest queue risk first");
    expect(rowOrder(out).slice(0, 4)).toEqual(["Pemogan", "MT Haryono", "Makassar", "Lingkar Selatan"]);
    expect(rowOrder(out).slice(-3)).toEqual(["Antasari", "Bandung", "KM57A"]);
  });

  it("has no sort or filter controls", () => {
    const text = textOf(html(<OverviewView {...props()} />));
    for (const gone of ["Worst first", "Slowed only", "Stations at a glance"]) expect(text).not.toContain(gone);
  });

  it("traffic now keeps today's summary and orders worst first", () => {
    const latest = indexLatest([reading("34.401.16-a", { congestion_index: 3.5, delay_s: 50 })]);
    const out = html(<OverviewView {...props({ mode: "now", latest })} />);
    expect(textOf(out)).toContain("sites slowed");
    expect(textOf(out)).toContain("Stations, worst traffic first");
    expect(rowOrder(out)[0]).toBe("Bandung");
  });

  it("falls back to traffic now with a notice when queue risk fails", () => {
    expect(effectiveMode("risk", new Error("x"))).toBe("now");
    expect(effectiveMode("risk", RISK)).toBe("risk");
    const out = html(<OverviewView {...props({ station: { risk: new Error("The server had a problem (HTTP 500)."), themes: THEMES } })} />);
    const text = textOf(out);
    expect(out).toContain('role="alert"');
    expect(text).toContain("Couldn't load the slowdown comparison, so the map shows traffic now. The server had a problem (HTTP 500).");
    expect(text).toContain("Waiting for the first traffic readings"); // today's summary line, no risk summary
    expect(text).not.toContain("Queue risk");
    expect(text).not.toContain(RISK_GUIDANCE);
    expect(text).not.toContain("Slowdown comparison unavailable"); // rows are traffic-now rows
    expect(text).toContain("Approach No data");
  });

  it("rates by traffic alone with a notice when review themes fail", () => {
    const out = html(<OverviewView {...props({ station: { risk: RISK, themes: new Error("No connection") } })} />);
    const text = textOf(out);
    expect(text).toContain("Couldn't load review counts, so queue risk comes from traffic only. No connection");
    expect(text).toContain("4 queue risk · 3 busy road · 3 low");
    expect(text).toContain("Reviews unavailable");
  });

  it("shows skeleton rows until both endpoints settle", () => {
    for (const station of [{ risk: undefined, themes: THEMES }, { risk: RISK, themes: undefined }] as StationData[]) {
      const out = html(<OverviewView {...props({ station })} />);
      expect(out).toContain('aria-label="Loading stations"');
      expect(textOf(out)).toContain("Loading stations…");
      expect(rowOrder(out)).toHaveLength(0);
    }
  });

  it("expands the selected station only", () => {
    const out = html(<OverviewView {...props({ selected: "74.902.22" })} />);
    expect(out.match(/aria-expanded="true"/g)).toHaveLength(1);
    expect(out).toMatch(/data-site-id="74.902.22" data-selected=""/);
  });

  it("never says queue in a traffic line", () => {
    const out = html(<OverviewView {...props()} />);
    const lines = [...out.matchAll(/data-signal="traffic">([^<]*)</g)].map((m) => m[1]);
    expect(lines).toHaveLength(10);
    for (const line of lines) expect(line).not.toMatch(/queue/i);
  });
});

describe("selection", () => {
  it("a row selects, and the same row again clears", () => {
    const s1 = selectionReducer(null, { type: "toggle", siteId: "a" });
    expect(s1).toBe("a");
    expect(selectionReducer(s1, { type: "toggle", siteId: "b" })).toBe("b");
    expect(selectionReducer(s1, { type: "toggle", siteId: "a" })).toBeNull();
  });
  it("a marker selects without toggling off", () => {
    expect(selectionReducer("a", { type: "select", siteId: "a" })).toBe("a");
    expect(selectionReducer(null, { type: "select", siteId: "b" })).toBe("b");
  });
  it("Escape clears", () => {
    expect(selectionReducer("a", { type: "clear" })).toBeNull();
  });
});

describe("map key and markers", () => {
  it("the queue-risk key lists the five labels in list order, red first", () => {
    const out = renderToStaticMarkup(<QueueLegend />);
    expect([...out.matchAll(/data-risk="(\w+)"/g)].map((m) => m[1])).toEqual(RISK_ORDER);
    expect([...out.matchAll(/data-level="(\w+)"/g)].map((m) => m[1])).toEqual(["red", "red", "red", "yellow", "green"]);
    for (const label of Object.values(RISK_LABELS)) expect(out).toContain(label);
  });
  it("a marker carries its level's text and icon, and a ring when selected", () => {
    const out = renderToStaticMarkup(<QueueMarker risk="both" text="Both" selected />);
    expect(out).toContain('data-risk="both"');
    expect(out).toContain('data-level="red"');
    expect(out).toContain("map-marker-selected");
    expect(out).toContain('class="queue-icon"');
    expect(out).toContain("Both");
    expect(renderToStaticMarkup(<QueueMarker risk="low" text="Low" compact />)).toContain('class="visually-hidden">Low');
  });
});

describe("SiteWeatherCell", () => {
  const weather = (over: Partial<WeatherLatest> = {}) =>
    ({ site_id: "a", slot_time: "2026-10-07T07:30:00Z", temperature_c: 30.4, demo_icon_uri: null, demo_condition_text: null, ...over }) as WeatherLatest;
  it("shows temperature without any demo mark when there is no icon", () => {
    const out = renderToStaticMarkup(<SiteWeatherCell now={weather()} />);
    expect(out).toContain("30 °C");
    expect(out).not.toContain("demo");
  });
  it("marks the condition icon (demo-only) and never the temperature", () => {
    const out = renderToStaticMarkup(<SiteWeatherCell now={weather({ demo_icon_uri: "https://x/sunny", demo_condition_text: "Sunny" })} />);
    expect(out).toContain('alt="Sunny"');
    expect(out).toMatch(/site-weather-icon.*demo-marker/);
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
