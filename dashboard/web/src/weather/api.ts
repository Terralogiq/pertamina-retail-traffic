// Client for /api/weather/* and /api/rain. Field names follow the API; `demo_*` fields are demo-only (see fields.ts).
import { getJson } from "../api";

export interface WeatherSlot {
  site_id: string;
  slot_time: string; // ISO 8601, UTC
  temperature_c: number | null;
  relative_humidity: number | null;
  precipitation_mm: number | null;
  rain_flag: boolean | null;
  wind_speed_kmh: number | null;
}

/** GET /api/weather/latest: latest slot per site in the last 2 h. */
export interface WeatherLatest extends WeatherSlot {
  demo_condition_type: string | null;
  demo_condition_text: string | null;
  demo_icon_uri: string | null;
  demo_rain_flag: boolean | null;
  demo_precip_probability: number | null;
}

/** GET /api/weather/series: one row per slot. */
export interface WeatherSeriesPoint extends WeatherSlot {
  demo_rain_flag: boolean | null;
  demo_precip_probability: number | null;
}

export interface DelayStat {
  mean_delay_s: number | null;
  n: number;
}

export interface RainSplit {
  site_id: string;
  leg: string;
  rain: DelayStat;
  dry: DelayStat;
}

export interface ScatterPoint {
  site_id: string;
  leg: string;
  precipitation_mm: number;
  congestion_index: number;
}

/** GET /api/rain: `core` splits by rain_flag, `demo` by demo_rain_flag. */
export interface RainResponse {
  site_id: string | null;
  days: number;
  core: RainSplit[];
  demo: RainSplit[];
  scatter: ScatterPoint[];
}

export interface SiteInfo {
  site_id: string;
  name: string;
  timezone: string;
}

export const getWeatherLatest = () => getJson<WeatherLatest[]>("/api/weather/latest");

export function getWeatherSeries(siteId: string, from?: string, to?: string) {
  const q = new URLSearchParams({ site_id: siteId });
  if (from) q.set("from", from);
  if (to) q.set("to", to);
  return getJson<WeatherSeriesPoint[]>(`/api/weather/series?${q}`);
}

export function getRain(days: number, siteId?: string) {
  const q = new URLSearchParams({ days: String(days) });
  if (siteId) q.set("site_id", siteId);
  return getJson<RainResponse>(`/api/rain?${q}`);
}

export const getSites = () => getJson<SiteInfo[]>("/api/sites");
