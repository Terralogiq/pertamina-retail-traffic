// Pure helpers for the map: colour bands, GeoJSON conversion, bounds, formatting. No Google Maps types at runtime.
import type { LatestLeg, Site } from "./api";

/** The baseline counts as full at 90% of 7 days x 48 half-hour slots (336), so one missed slot does not hold a leg in fallback. */
export const BASELINE_FULL = 302;

export const GREY = "#9e9e9e";
const GREEN = "#2e9e4f";
const AMBER = "#f2b100";
const ORANGE = "#f57c00";
const RED = "#d32f2f";

export type Basis = "congestion" | "speed" | "none";

/** Congestion index (duration / baseline): <1.2 green, 1.2-1.6 amber, 1.6-2.2 orange, >=2.2 red. */
export const CONGESTION_BANDS = [
  { max: 1.2, color: GREEN, label: "< 1.2" },
  { max: 1.6, color: AMBER, label: "1.2 - 1.6" },
  { max: 2.2, color: ORANGE, label: "1.6 - 2.2" },
  { max: Infinity, color: RED, label: ">= 2.2" },
];

/** Speed fallback while the baseline is pending (urban roads, km/h): >=35 green, 25-35 amber, 15-25 orange, <15 red. */
export const SPEED_BANDS = [
  { max: 15, color: RED, label: "< 15 km/h" },
  { max: 25, color: ORANGE, label: "15 - 25 km/h" },
  { max: 35, color: AMBER, label: "25 - 35 km/h" },
  { max: Infinity, color: GREEN, label: ">= 35 km/h" },
];

export const congestionColor = (index: number): string => CONGESTION_BANDS.find((b) => index < b.max)!.color;
export const speedColor = (kmh: number): string => SPEED_BANDS.find((b) => kmh < b.max)!.color;

/** Colour of a leg and what it is based on. Congestion only with a full baseline; else speed; else grey. */
export function legColor(latest: LatestLeg | undefined): { color: string; basis: Basis } {
  if (latest) {
    if (latest.congestion_index != null && (latest.baseline_samples ?? 0) >= BASELINE_FULL) {
      return { color: congestionColor(latest.congestion_index), basis: "congestion" };
    }
    if (latest.speed_kmh != null) return { color: speedColor(latest.speed_kmh), basis: "speed" };
  }
  return { color: GREY, basis: "none" };
}

/** Latest row per selected_route_id (keeps the newest slot_time if a leg appears twice). */
export function indexLatest(rows: LatestLeg[]): Map<string, LatestLeg> {
  const out = new Map<string, LatestLeg>();
  for (const row of rows) {
    const seen = out.get(row.selected_route_id);
    if (!seen || Date.parse(row.slot_time) > Date.parse(seen.slot_time)) out.set(row.selected_route_id, row);
  }
  return out;
}

/** Rows of a site's legs, in leg order, skipping legs with no row yet. */
export function siteLatest(site: Site, latest: Map<string, LatestLeg>): LatestLeg[] {
  return site.legs.flatMap((leg) => latest.get(leg.selected_route_id) ?? []);
}

/** Baseline progress for a site: the lowest baseline_samples over its legs with data; null when there is no data. */
export function baselineProgress(rows: LatestLeg[]): number | null {
  if (rows.length === 0) return null;
  return Math.min(...rows.map((r) => Math.min(r.baseline_samples ?? 0, BASELINE_FULL)));
}

export function baselineBadge(progress: number | null): string | null {
  return progress !== null && progress < BASELINE_FULL ? `baseline building (${progress}/${BASELINE_FULL})` : null;
}

export interface LatLng {
  lat: number;
  lng: number;
}

/** GeoJSON LineString ([lng, lat] order) -> LatLng path. */
export function lineToPath(line: { coordinates: number[][] } | null | undefined): LatLng[] {
  return (line?.coordinates ?? []).map(([lng, lat]) => ({ lat, lng }));
}

/** Every point that should be visible for these sites: the SPBU location plus all leg vertices. */
export function sitePoints(sites: Site[]): LatLng[] {
  return sites.flatMap((s) => [s.location, ...s.legs.flatMap((l) => lineToPath(l.expected_polyline))]);
}

export interface Bounds {
  north: number;
  south: number;
  east: number;
  west: number;
}

/** Bounding box for map.fitBounds; null for no points. (Ignores the antimeridian; Indonesia does not cross it.) */
export function boundsOf(points: LatLng[]): Bounds | null {
  if (points.length === 0) return null;
  const lats = points.map((p) => p.lat);
  const lngs = points.map((p) => p.lng);
  return { north: Math.max(...lats), south: Math.min(...lats), east: Math.max(...lngs), west: Math.min(...lngs) };
}

/** "+1.5 min", "+45 s", "-20 s"; "-" when unknown. */
export function formatDelay(delayS: number | null | undefined): string {
  if (delayS == null) return "-";
  const sign = delayS < 0 ? "-" : "+";
  const abs = Math.abs(delayS);
  return abs < 60 ? `${sign}${Math.round(abs)} s` : `${sign}${(abs / 60).toFixed(1)} min`;
}

export const formatSpeed = (kmh: number | null | undefined): string => (kmh == null ? "-" : `${Math.round(kmh)} km/h`);

const TZ_LABELS: Record<string, string> = { "Asia/Jakarta": "WIB", "Asia/Makassar": "WITA", "Asia/Jayapura": "WIT" };

/** Slot time in the site's local time, e.g. "14:30 WIB". */
export function formatSlot(slotTime: string, timezone: string): string {
  const time = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timezone,
  }).format(new Date(slotTime));
  return `${time} ${TZ_LABELS[timezone] ?? timezone}`;
}

export const legLabel = (leg: string): string => leg.charAt(0).toUpperCase() + leg.slice(1);
