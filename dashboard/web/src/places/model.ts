// Pure helpers behind the Places panel.
import type { CompetitorCount, CompetitorTotal, PlaceReview, PoiCount } from "./api";

export const REVIEW_LIMIT = 5;
export const COMPETITOR_RADII = [1000, 3000];
export const POI_RADII = [500, 1000, 3000];

export const radiusLabel = (m: number) => (m % 1000 === 0 ? `${m / 1000} km` : `${m} m`);

/** "★★★★☆" for a 1-5 rating; "n/a" when missing. */
export function stars(rating: number | null | undefined): string {
  if (rating == null) return "n/a";
  const n = Math.max(0, Math.min(5, Math.round(rating)));
  return "★".repeat(n) + "☆".repeat(5 - n);
}

/** "2026-09-20": the calendar day in UTC (locale-independent). Empty string when missing. */
export const formatDate = (iso: string | null | undefined) => (iso ? new Date(iso).toISOString().slice(0, 10) : "");

/** The newest `limit` reviews, whatever order they arrive in (missing dates last). */
export function latestReviews(reviews: PlaceReview[], limit = REVIEW_LIMIT): PlaceReview[] {
  const time = (r: PlaceReview) => (r.publish_time ? Date.parse(r.publish_time) : -Infinity);
  return [...reviews].sort((a, b) => time(b) - time(a)).slice(0, limit);
}

/** "19*" when the radius was capped (the count is a lower bound), else "7". */
export const totalLabel = (t: CompetitorTotal) => `${t.total}${t.capped ? "*" : ""}`;

export interface BrandRow {
  brand: string;
  counts: (number | null)[]; // one per radius, null when that radius has no row
}

/** Brand x radius grid in API brand order; radii are the columns in `radii`. */
export function competitorRows(competitors: CompetitorCount[], radii = COMPETITOR_RADII): BrandRow[] {
  const brands: string[] = [];
  for (const c of competitors) if (!brands.includes(c.brand)) brands.push(c.brand);
  return brands.map((brand) => ({
    brand,
    counts: radii.map((r) => competitors.find((c) => c.brand === brand && c.radius_m === r)?.count ?? null),
  }));
}

export interface PoiRow {
  place_type: string;
  counts: (number | null)[]; // one per radius
}

/** Readable names for the Places Aggregate types, grouped for the POI table (F17). Unknown types fall into Other. */
export const POI_GROUPS: { group: string; types: Record<string, string> }[] = [
  { group: "Food and drink", types: { restaurant: "Restaurants", cafe: "Cafés" } },
  { group: "Shopping", types: { convenience_store: "Convenience stores", supermarket: "Supermarkets", shopping_mall: "Shopping malls" } },
  { group: "Education and health", types: { school: "Schools", university: "Universities", hospital: "Hospitals" } },
  { group: "Money", types: { bank: "Banks", atm: "ATMs" } },
  { group: "Stay", types: { lodging: "Lodging" } },
  {
    group: "Vehicles",
    types: {
      gas_station: "Gas stations",
      car_repair: "Car repair",
      car_wash: "Car washes",
      electric_vehicle_charging_station: "EV charging",
    },
  },
];

/** "car_repair" -> "Car repair" for a type no group names. */
export const humanType = (t: string) => {
  for (const g of POI_GROUPS) if (t in g.types) return g.types[t];
  const s = t.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
};

/** POI rows grouped and labelled, groups in POI_GROUPS order, rows in each group's order; empty groups dropped. */
export function groupedPoiRows(rows: PoiRow[]): { group: string; rows: (PoiRow & { label: string })[] }[] {
  const known = new Set(POI_GROUPS.flatMap((g) => Object.keys(g.types)));
  const groups = POI_GROUPS.map((g) => ({
    group: g.group,
    rows: Object.keys(g.types).flatMap((t) => {
      const row = rows.find((r) => r.place_type === t);
      return row ? [{ ...row, label: g.types[t] }] : [];
    }),
  }));
  const other = rows.filter((r) => !known.has(r.place_type)).map((r) => ({ ...r, label: humanType(r.place_type) }));
  return [...groups, { group: "Other", rows: other }].filter((g) => g.rows.length > 0);
}

/**
 * One line when every day has the same hours (F17): "Open 24 hours, every day" for 24-hour stations
 * (Places writes "Buka 24 jam" or "Open 24 hours"), else "<hours>, every day". null when the days differ or none are stored.
 */
export function collapsedHours(lines: string[]): string | null {
  if (lines.length !== 7) return null;
  const hours = lines.map((l) => l.slice(l.indexOf(":") + 1).trim());
  if (new Set(hours).size !== 1) return null;
  return /24\s*(jam|hours)/i.test(hours[0]) ? "Open 24 hours, every day" : `${hours[0]}, every day`;
}

/** "3 weeks ago" against `now`; the absolute day stays in the <time> element. */
export function relativeDate(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "";
  const days = Math.round((Date.parse(iso) - now.getTime()) / 86400000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (Math.abs(days) < 7) return rtf.format(days, "day");
  if (Math.abs(days) < 30) return rtf.format(Math.round(days / 7), "week");
  if (Math.abs(days) < 365) return rtf.format(Math.round(days / 30), "month");
  return rtf.format(Math.round(days / 365), "year");
}

/** "OPERATIONAL" -> "Operational", "CLOSED_TEMPORARILY" -> "Closed temporarily". */
export const humanStatus = (s: string | null | undefined) => (s ? humanType(s.toLowerCase()) : "");

/** "7 Oct 2026" for the Places run date (UTC calendar day). */
export const longDate = (iso: string | null | undefined) =>
  iso ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(iso)) : "";

/** Type x radius grid, types in API order (alphabetical). */
export function poiRows(poi: PoiCount[], radii = POI_RADII): PoiRow[] {
  const types: string[] = [];
  for (const p of poi) if (!types.includes(p.place_type)) types.push(p.place_type);
  return types.map((place_type) => ({
    place_type,
    counts: radii.map((r) => poi.find((p) => p.place_type === place_type && p.radius_m === r)?.count ?? null),
  }));
}
