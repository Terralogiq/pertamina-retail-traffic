import { BASELINE_FULL, formatDelay } from "../map/bands";
import type { WeatherSeriesPoint } from "../weather/api";
import type { TrafficPoint } from "./api";

// One threshold for the map badge and the charts: 90% of a 7-day window (see map/bands.ts).
// formatDelay is the one delay format ("+16 s", "+1.3 min"); the map list and the site header must agree.
export { BASELINE_FULL, formatDelay };

export type Range = "24h" | "7d";
const RANGE_HOURS: Record<Range, number> = { "24h": 24, "7d": 168 };
const SLOT_MS = 30 * 60 * 1000;

export type MetricField = "congestion_index" | "delay_s" | "speed_kmh";

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

/** One delay-chart point: the plotted delay, plus the speed and usual-time multiple the tooltip shows. */
export interface DelayDatum {
  value: [number, number | null];
  speed_kmh: number | null;
  congestion_index: number | null;
}

/** Delay lines, one per leg, timestamps shifted the same way as legSeries. */
export function delaySeries(points: TrafficPoint[], offsetMin: number): { leg: string; data: DelayDatum[] }[] {
  const byLeg = new Map<string, DelayDatum[]>();
  for (const p of points) {
    const data = byLeg.get(p.leg) ?? [];
    data.push({
      value: [Date.parse(p.slot_time) + offsetMin * 60 * 1000, p.delay_s],
      speed_kmh: p.speed_kmh,
      congestion_index: p.congestion_index,
    });
    byLeg.set(p.leg, data);
  }
  return [...byLeg].map(([leg, data]) => ({ leg, data: data.sort((a, b) => a.value[0] - b.value[0]) }));
}

/** Tooltip line for the delay chart: delay, speed, and how many times the usual travel time. */
export function delayTooltipText(
  name: string,
  delayS: number | null,
  speedKmh: number | null,
  congestionIndex: number | null,
): string {
  const delay = delayS == null ? "n/a" : formatDelay(delayS);
  const speed = speedKmh == null ? "n/a" : `${Math.round(speedKmh)} km/h`;
  const usual = congestionIndex == null ? "n/a" : `${congestionIndex.toFixed(2)}× usual time`;
  return `${name}: ${delay} · ${speed} · ${usual}`;
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

/** True when any slot in the window had measurable rain; a window of zeros gets a note, not an empty axis. */
export const hadRain = (rain: [number, number][]) => rain.some(([, mm]) => mm > 0);

export const legLabel = (leg: string) => leg.charAt(0).toUpperCase() + leg.slice(1);
