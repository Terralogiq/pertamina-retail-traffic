// Client for GET /api/places/analysis: POI counts vs traffic, one rank correlation per (group, radius).
// Core columns and Places data only, so nothing on this screen is demo-only.
import { getJson } from "../api";

export type PoiMetric = "delay" | "peak" | "busy";
export type PoiLeg = "both" | "approach" | "departure";

/** Spearman rho with its 95% bootstrap interval, permutation p and leave-one-out range. All null when it cannot be computed. */
export interface PoiStat {
  group: string;
  radius_m: number;
  rho: number | null;
  ci_low: number | null;
  ci_high: number | null;
  p: number | null;
  loo_min: number | null;
  loo_max: number | null;
  n: number;
}

export interface PoiSite {
  site_id: string;
  name: string;
  city: string | null;
  road_class: "urban" | "toll";
  /** delay: mean s per km; peak: 95th percentile of the congestion index; busy: weekday busy hours / 24. For the selected leg. */
  metrics: Record<PoiMetric, number | null>;
  busy_hours: { approach?: number | null; departure?: number | null };
  /** Count per group, one entry per radius in `radii` (null when missing); null when the site has no Places run. */
  poi: Record<string, (number | null)[]> | null;
}

export interface PoiAnalysis {
  metric: PoiMetric;
  leg: PoiLeg;
  exclude_toll: boolean;
  ready: boolean;
  days: number;
  ready_days: number;
  window: { from: string | null; to: string | null };
  places_run: string | null;
  groups: { id: string; label: string }[];
  radii: number[];
  sites: PoiSite[];
  stats: PoiStat[];
}

export function getPoiAnalysis(metric: PoiMetric, leg: PoiLeg, excludeToll: boolean) {
  const q = new URLSearchParams({ metric, leg, exclude_toll: String(excludeToll) });
  return getJson<PoiAnalysis>(`/api/places/analysis?${q}`);
}
