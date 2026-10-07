// Client for /api/places/{site_id}: the latest stored Places run of a site.
import { getJson } from "../api";

export interface PlaceReview {
  rating: number | null;
  text: string | null;
  language: string | null;
  publish_time: string | null; // ISO 8601, UTC
  author_name: string | null;
}

export interface PlaceDetails {
  display_name: string | null;
  rating: number | null;
  user_rating_count: number | null;
  business_status: string | null;
  open_now: boolean | null;
  weekday_descriptions: string[];
  reviews: PlaceReview[]; // newest first
}

/** Gas stations of one brand in the Nearby Search around the site, the site's own place excluded. */
export interface CompetitorCount {
  radius_m: number;
  brand: string;
  count: number;
}

/** `capped`: the radius returned the maximum of 20 results (site included), so the total is a lower bound. */
export interface CompetitorTotal {
  radius_m: number;
  total: number;
  capped: boolean;
}

export interface PoiCount {
  place_type: string;
  radius_m: number;
  count: number | null;
}

/** `run_id`, `fetched_at` and `details` are null when the site has no run in the lookback window. */
export interface PlacesResponse {
  site_id: string;
  run_id: string | null;
  fetched_at: string | null;
  details: PlaceDetails | null;
  competitors: CompetitorCount[];
  competitor_totals: CompetitorTotal[];
  poi: PoiCount[];
}

export const getPlaces = (siteId: string) => getJson<PlacesResponse>(`/api/places/${encodeURIComponent(siteId)}`);
