// Pure helpers for the map: colour bands, GeoJSON conversion, bounds, formatting. No Google Maps types at runtime.
import type { LatestLeg, Site } from "./api";
import { BANDS, BandId } from "../theme/palette";

/** The baseline counts as full at 90% of 7 days x 48 half-hour slots (336), so one missed slot does not hold a leg in fallback. */
export const BASELINE_FULL = 302;

export const GREY = BANDS.none.color;

export type Basis = "congestion" | "speed" | "none";
export type RoadClass = "urban" | "toll";

/** A reading stays Free flow unless it is both at least this multiple of usual time and over the delay gate. */
export const BAND_CUTS = { moderate: 1.5, heavy: 2, jam: 3 } as const;
export const DELAY_GATE_S: Record<RoadClass, number> = { urban: 20, toll: 30 };
/** Usual speed while the 7-day baseline is still building. */
export const PROVISIONAL_KMH: Record<RoadClass, number> = { urban: 45, toll: 80 };

/** Toll when the CSV road type mentions a toll road; every other label is urban. */
export const roadClassOf = (roadType: string | null | undefined): RoadClass =>
  (roadType ?? "").toLowerCase().includes("toll") ? "toll" : "urban";

export interface LegContext {
  roadClass: RoadClass;
  expectedDistanceM: number | null;
}

export function legContext(site: Site, routeId: string): LegContext {
  const leg = site.legs.find((l) => l.selected_route_id === routeId);
  return { roadClass: site.road_class, expectedDistanceM: leg?.expected_distance_m ?? null };
}

/** Free flow under 1.5× or under the delay gate; then 1.5–2 moderate, 2–3 heavy, 3 and over jammed. */
export function bandOf(index: number, delayS: number, roadClass: RoadClass): BandId {
  if (!(index >= BAND_CUTS.moderate && delayS >= DELAY_GATE_S[roadClass])) return "free";
  if (index < BAND_CUTS.heavy) return "moderate";
  if (index < BAND_CUTS.jam) return "heavy";
  return "jam";
}

export const CONGESTION_BANDS: { band: BandId; label: string }[] = [
  { band: "free", label: "under 1.5×, or under the delay gate" },
  { band: "moderate", label: "1.5 to 2×" },
  { band: "heavy", label: "2 to 3×" },
  { band: "jam", label: "3× and over" },
];

function provisional(durationS: number, distanceM: number, roadClass: RoadClass): { index: number; delayS: number } {
  const freeS = distanceM / ((PROVISIONAL_KMH[roadClass] * 1000) / 3600);
  return { index: durationS / freeS, delayS: durationS - freeS };
}

/**
 * Band of a leg and what it is based on. A full baseline uses congestion_index and delay_s.
 * While the baseline builds, the same cuts apply to duration against the road class's provisional speed.
 */
export function legBand(latest: LatestLeg | undefined, ctx?: LegContext): { band: BandId; basis: Basis } {
  if (!latest) return { band: "none", basis: "none" };
  const road = ctx?.roadClass ?? "urban";
  const full = (latest.baseline_samples ?? 0) >= BASELINE_FULL;
  if (full && latest.congestion_index != null && latest.delay_s != null) {
    return { band: bandOf(latest.congestion_index, latest.delay_s, road), basis: "congestion" };
  }
  const distance = ctx?.expectedDistanceM;
  if (!full && latest.duration_s != null && distance != null && distance > 0) {
    const { index, delayS } = provisional(latest.duration_s, distance, road);
    return { band: bandOf(index, delayS, road), basis: "speed" };
  }
  return { band: "none", basis: "none" };
}

/** Colour of a leg and its basis (the map's polylines). */
export function legColor(latest: LatestLeg | undefined, ctx?: LegContext): { color: string; basis: Basis } {
  const { band, basis } = legBand(latest, ctx);
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

/** "+1.5 min", "+45 s", "no delay" at or below zero; "-" when unknown. */
export function formatDelay(delayS: number | null | undefined): string {
  if (delayS == null) return "-";
  if (delayS <= 0) return "no delay";
  return delayS < 60 ? `+${Math.round(delayS)} s` : `+${(delayS / 60).toFixed(1)} min`;
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
