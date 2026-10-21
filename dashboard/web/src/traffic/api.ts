import { getJson } from "../api";
import type { QueueRiskSite } from "../overview/api";

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

export const getTrafficSeries = (siteId: string, from: string, to?: string) => {
  const q = new URLSearchParams({ site_id: siteId, from });
  if (to) q.set("to", to);
  return getJson<TrafficPoint[]>(`/api/traffic/series?${q}`);
};

export const getTrafficPattern = (siteId: string, days = 28) =>
  getJson<PatternCell[]>(`/api/traffic/pattern?${new URLSearchParams({ site_id: siteId, days: String(days) })}`);

export type DayKind = "weekday" | "weekend";

/** One local hour of GET /api/traffic/typical-day. `faded` is n < 4. `busy` uses the map band rule. */
export interface TypicalHour {
  hour: number;
  median_delay_s: number | null;
  p25_delay_s: number | null;
  p75_delay_s: number | null;
  n: number;
  faded: boolean;
  busy: boolean;
}

/** Consecutive busy hours. `end_hour` is exclusive; a midnight wrap has end_hour < start_hour. A full day is 0–24. */
export interface BusyWindow {
  start_hour: number;
  end_hour: number;
  median_delay_s: number | null;
}

/** One leg and day kind, with hours 0–23. `windows` is empty until the profile is ready. */
export interface TypicalLeg {
  leg: string;
  day_kind: DayKind;
  hours: TypicalHour[];
  windows: BusyWindow[];
}

/** Median delay by local hour over the last 28 days. `ready` is days >= 7. */
export interface TypicalDayResponse {
  days: number;
  ready: boolean;
  legs: TypicalLeg[];
}

export const getTypicalDay = (siteId: string) =>
  getJson<TypicalDayResponse>(`/api/traffic/typical-day?${new URLSearchParams({ site_id: siteId })}`);

/** One local hour of the queue-risk strip. `als_pct` is the share of readings slower before the station than after it. */
export interface AlsHour {
  hour: number;
  n: number;
  als_n: number;
  als_pct: number | null;
  /** n < 4 */
  faded: boolean;
  approach_median_delay_s: number | null;
  /** Busy on the approach under the busy-hour rule while the departure is not. */
  approach_only_busy: boolean;
}

/** Hours 0–23 for one day kind, with the consecutive approach-only busy hours as windows (`end_hour` exclusive). */
export interface AlsDayKind {
  day_kind: DayKind;
  hours: AlsHour[];
  windows: BusyWindow[];
}

/** GET /api/traffic/queue-risk?site_id=: the all-sites entry plus the longest run (hours) and the per-hour strip. */
export interface QueueRiskSiteDetail extends QueueRiskSite {
  /** Local dates with a paired reading. `ready` is days >= 7; until then no hour is flagged busy and `windows` are empty. */
  days: number;
  ready: boolean;
  longest_run_h: number;
  day_kinds: AlsDayKind[];
}

/** `sites` is empty when the site has no paired reading in the window. */
export interface QueueRiskSiteResponse {
  window_days: number;
  sites: QueueRiskSiteDetail[];
}

export const getQueueRiskSite = (siteId: string) =>
  getJson<QueueRiskSiteResponse>(`/api/traffic/queue-risk?${new URLSearchParams({ site_id: siteId })}`);
