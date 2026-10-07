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

/** Type x radius grid, types in API order (alphabetical). */
export function poiRows(poi: PoiCount[], radii = POI_RADII): PoiRow[] {
  const types: string[] = [];
  for (const p of poi) if (!types.includes(p.place_type)) types.push(p.place_type);
  return types.map((place_type) => ({
    place_type,
    counts: radii.map((r) => poi.find((p) => p.place_type === place_type && p.radius_m === r)?.count ?? null),
  }));
}
