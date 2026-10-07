import { getJson } from "../api";

/** One slot of one leg; the shape of GET /api/traffic/series and /api/traffic/latest. */
export interface TrafficPoint {
  selected_route_id: string;
  site_id: string;
  leg: string;
  slot_time: string; // ISO UTC
  duration_s: number | null;
  delay_s: number | null;
  congestion_index: number | null;
  speed_kmh: number | null;
  baseline_samples: number | null;
}

/** One cell of GET /api/traffic/pattern: dow 1 = Monday .. 7 = Sunday, hour 0-23 in the site's local time. */
export interface PatternCell {
  dow: number;
  hour: number;
  leg: string;
  mean_congestion: number | null;
  mean_speed_kmh: number | null;
  n: number;
}

export interface SiteTimezone {
  site_id: string;
  timezone: string | null;
}

export const getTrafficSeries = (siteId: string, from: string, to?: string) => {
  const q = new URLSearchParams({ site_id: siteId, from });
  if (to) q.set("to", to);
  return getJson<TrafficPoint[]>(`/api/traffic/series?${q}`);
};

export const getTrafficPattern = (siteId: string, days = 28) =>
  getJson<PatternCell[]>(`/api/traffic/pattern?${new URLSearchParams({ site_id: siteId, days: String(days) })}`);

/** The site list is cached server-side per slot; only the timezone is used here. */
export const getSiteTimezones = () => getJson<SiteTimezone[]>("/api/sites");
