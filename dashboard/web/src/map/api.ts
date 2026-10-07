import { getJson } from "../api";

export interface Leg {
  selected_route_id: string;
  display_name: string | null;
  side: string | null;
  leg: string; // "approach" | "departure"
  leg_index: number;
  expected_distance_m: number | null;
  expected_polyline: { type: "LineString"; coordinates: number[][] } | null; // GeoJSON, [lng, lat]
}

export interface Site {
  site_id: string;
  name: string;
  place_id: string;
  road_name: string | null;
  city: string | null;
  timezone: string; // IANA, e.g. Asia/Jakarta
  location: { lat: number; lng: number };
  legs: Leg[];
}

/** One row of GET /api/traffic/latest: the latest slot of one leg. Numbers may be null. */
export interface LatestLeg {
  selected_route_id: string;
  site_id: string;
  leg: string;
  slot_time: string; // ISO, UTC
  duration_s: number | null;
  delay_s: number | null;
  congestion_index: number | null;
  speed_kmh: number | null;
  baseline_samples: number | null;
}

export const getSites = () => getJson<Site[]>("/api/sites");
export const getLatestTraffic = () => getJson<LatestLeg[]>("/api/traffic/latest");
