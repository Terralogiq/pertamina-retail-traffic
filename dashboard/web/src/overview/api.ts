// Clients for the overview station list: /api/traffic/queue-risk and /api/review-themes (all sites at once).
import { getJson } from "../api";

export type Tier = "strong" | "moderate" | "weak" | "none" | "cannot_tell";
export type ConfidenceLevel = "medium" | "low" | "very_low" | "none";

/** A judgement kept in a reference file (not computed); `as_of` is the date it was made. */
export interface Confidence {
  level: ConfidenceLevel;
  reason: string;
  as_of: string;
}

/** Road slowdown before the station compared with after it, over the rolling window. Not a car count. */
export interface QueueRiskSite {
  site_id: string;
  tier: Tier;
  als_pct: number;
  both_slow_pct: number;
  departure_only_pct: number;
  days_with_2h_als: number;
  full_days: number;
  als_median_delay_s: number | null;
  confidence: Confidence | null;
}

/** `sites` arrive in queue-risk order (tier, then days, then delay; cannot_tell last). */
export interface QueueRiskResponse {
  window_days: number;
  sites: QueueRiskSite[];
}

/** Counts from the sampled Google reviews. `top` lists every category tied for the highest count. */
export interface StationThemes {
  site_id: string;
  n_labelled: number;
  queue_complaints: number;
  top: { categories: string[]; count: number } | null;
  categories: { category: string; count: number }[];
  /** Negative or mixed reviews from the last 12 months labelled `antrian`. */
  queue_recent: number;
  /** Reviews from the last 12 months that say the queue reaches the road. */
  road_queue_recent: number;
}

export interface StationThemesResponse {
  sites: StationThemes[];
}

export const getQueueRisk = () => getJson<QueueRiskResponse>("/api/traffic/queue-risk");
export const getStationThemes = () => getJson<StationThemesResponse>("/api/review-themes");
