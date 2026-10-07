// Pure helpers for the map: colour bands, GeoJSON conversion, bounds, formatting. No Google Maps types at runtime.
import type { LatestLeg, Site } from "./api";
import { BANDS, BandId } from "../theme/palette";

/** The baseline counts as full at 90% of 7 days x 48 half-hour slots (336), so one missed slot does not hold a leg in fallback. */
export const BASELINE_FULL = 302;

export const GREY = BANDS.none.color;

export type Basis = "congestion" | "speed" | "none";

/** Congestion index (duration / baseline): <1.2 free, 1.2-1.6 moderate, 1.6-2.2 heavy, >=2.2 jammed. */
export const CONGESTION_BANDS: { max: number; band: BandId; label: string }[] = [
  { max: 1.2, band: "free", label: "under 1.2" },
  { max: 1.6, band: "moderate", label: "1.2 to 1.6" },
  { max: 2.2, band: "heavy", label: "1.6 to 2.2" },
  { max: Infinity, band: "jam", label: "2.2 and over" },
];

/** Speed fallback while the baseline is pending (urban roads, km/h): >=35 free, 25-35 moderate, 15-25 heavy, <15 jammed. */
export const SPEED_BANDS: { max: number; band: BandId; label: string }[] = [
  { max: 15, band: "jam", label: "under 15 km/h" },
  { max: 25, band: "heavy", label: "15 to 25 km/h" },
  { max: 35, band: "moderate", label: "25 to 35 km/h" },
  { max: Infinity, band: "free", label: "35 km/h and over" },
];

export const congestionBand = (index: number): BandId => CONGESTION_BANDS.find((b) => index < b.max)!.band;
export const speedBand = (kmh: number): BandId => SPEED_BANDS.find((b) => kmh < b.max)!.band;
export const congestionColor = (index: number): string => BANDS[congestionBand(index)].color;
export const speedColor = (kmh: number): string => BANDS[speedBand(kmh)].color;

/** Band of a leg and what it is based on. Congestion only with a full baseline; else speed; else no data. */
export function legBand(latest: LatestLeg | undefined): { band: BandId; basis: Basis } {
  if (latest) {
    if (latest.congestion_index != null && (latest.baseline_samples ?? 0) >= BASELINE_FULL) {
      return { band: congestionBand(latest.congestion_index), basis: "congestion" };
    }
    if (latest.speed_kmh != null) return { band: speedBand(latest.speed_kmh), basis: "speed" };
  }
  return { band: "none", basis: "none" };
}

/** Colour of a leg and its basis (the map's polylines). */
export function legColor(latest: LatestLeg | undefined): { color: string; basis: Basis } {
  const { band, basis } = legBand(latest);
  return { color: BANDS[band].color, basis };
}

/** Severity order, worst last: no data sorts below free flow so a silent site never hides a slow one. */
export const BAND_RANK: Record<BandId, number> = { none: 0, free: 1, moderate: 2, heavy: 3, jam: 4 };

/** Bands that count as "slowed" in the overview summary. */
export const isSlowed = (band: BandId): boolean => BAND_RANK[band] >= BAND_RANK.moderate;

/** Latest row per selected_route_id (keeps the newest slot_time if a leg appears twice). */
export function indexLatest(rows: LatestLeg[]): Map<string, LatestLeg> {
  const out = new Map<string, LatestLeg>();
  for (const row of rows) {
    const seen = out.get(row.selected_route_id);
    if (!seen || Date.parse(row.slot_time) > Date.parse(seen.slot_time)) out.set(row.selected_route_id, row);
  }
  return out;
}

/** Baseline progress for a site: the lowest baseline_samples over its legs with data; null when there is no data. */
export function baselineProgress(rows: LatestLeg[]): number | null {
  if (rows.length === 0) return null;
  return Math.min(...rows.map((r) => Math.min(r.baseline_samples ?? 0, BASELINE_FULL)));
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
