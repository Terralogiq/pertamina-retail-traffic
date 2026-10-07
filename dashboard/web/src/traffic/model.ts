import { BASELINE_FULL } from "../map/bands";
import type { WeatherSeriesPoint } from "../weather/api";
import type { PatternCell, TrafficPoint } from "./api";

// One threshold for the map badge and the charts: 90% of a 7-day window (see map/bands.ts).
export { BASELINE_FULL };

export type Range = "24h" | "7d";
const RANGE_HOURS: Record<Range, number> = { "24h": 24, "7d": 168 };
const SLOT_MS = 30 * 60 * 1000;

export const METRICS = [
  { field: "congestion_index", title: "Congestion index", unit: "" },
  { field: "delay_s", title: "Delay", unit: "s" },
  { field: "speed_kmh", title: "Speed", unit: "km/h" },
] as const;
export type MetricField = (typeof METRICS)[number]["field"];

export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Start of the series window, floored to the half hour so repeated views share a server-side cache entry. */
export function windowStart(range: Range, now: Date): string {
  const floored = Math.floor(now.getTime() / SLOT_MS) * SLOT_MS;
  return new Date(floored - RANGE_HOURS[range] * 3600 * 1000).toISOString();
}

const TZ_LABELS: Record<string, string> = { "Asia/Jakarta": "WIB", "Asia/Makassar": "WITA" };

/** WIB / WITA for the two Indonesian zones this app uses; the IANA name otherwise; UTC when unknown. */
export function tzLabel(timezone: string | null | undefined): string {
  if (!timezone) return "UTC";
  return TZ_LABELS[timezone] ?? timezone;
}

/** Offset of `timezone` from UTC in minutes at `at` (Indonesia has no DST); 0 when unknown or invalid. */
export function utcOffsetMinutes(timezone: string | null | undefined, at: Date): number {
  if (!timezone) return 0;
  try {
    const parts = new Intl.DateTimeFormat("en-US", { timeZone: timezone, timeZoneName: "longOffset" }).formatToParts(at);
    const name = parts.find((p) => p.type === "timeZoneName")?.value ?? "";
    const m = /^GMT([+-])(\d{2}):(\d{2})$/.exec(name);
    if (!m) return 0;
    return (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3]));
  } catch {
    return 0;
  }
}

/**
 * Lines for one metric, one per leg: [timestamp, value] with timestamps shifted by the site's UTC offset.
 * A chart with `useUTC` then draws site-local clock time.
 */
export function legSeries(
  points: TrafficPoint[],
  field: MetricField,
  offsetMin: number,
): { leg: string; data: [number, number | null][] }[] {
  const byLeg = new Map<string, [number, number | null][]>();
  for (const p of points) {
    const data = byLeg.get(p.leg) ?? [];
    data.push([Date.parse(p.slot_time) + offsetMin * 60 * 1000, p[field]]);
    byLeg.set(p.leg, data);
  }
  return [...byLeg].map(([leg, data]) => ({ leg, data: data.sort((a, b) => a[0] - b[0]) }));
}

/**
 * Precipitation bars as [timestamp, mm], shifted by the same site UTC offset as legSeries so both share one time
 * axis. Slots without a value are dropped (no bar rather than a zero-height one).
 */
export function precipitationSeries(slots: WeatherSeriesPoint[], offsetMin: number): [number, number][] {
  return slots
    .filter((w) => w.precipitation_mm !== null)
    .map((w): [number, number] => [Date.parse(w.slot_time) + offsetMin * 60 * 1000, w.precipitation_mm as number])
    .sort((a, b) => a[0] - b[0]);
}

/**
 * Samples behind the least-established baseline among the legs' latest slots (null baseline counts as 0),
 * or null once every leg has a full window (or there is no data).
 */
export function baselineBuilding(points: TrafficPoint[]): number | null {
  const latest = new Map<string, TrafficPoint>();
  for (const p of points) {
    const seen = latest.get(p.selected_route_id);
    if (!seen || p.slot_time > seen.slot_time) latest.set(p.selected_route_id, p);
  }
  if (latest.size === 0) return null;
  const n = Math.min(...[...latest.values()].map((p) => p.baseline_samples ?? 0));
  return n < BASELINE_FULL ? n : null;
}

/** Heatmap cells for one leg as [hour, dow - 1, mean congestion]; cells without a value are dropped. */
export function heatmapData(cells: PatternCell[], leg: string): [number, number, number][] {
  return cells
    .filter((c) => c.leg === leg && c.mean_congestion !== null)
    .map((c) => [c.hour, c.dow - 1, c.mean_congestion as number]);
}

export function patternLegs(cells: PatternCell[]): string[] {
  return [...new Set(cells.map((c) => c.leg))].sort();
}
