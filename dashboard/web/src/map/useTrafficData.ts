import { useEffect, useMemo, useState } from "react";
import { LatestLeg, Site, getLatestTraffic, getSites } from "./api";
import { WeatherLatest, getWeatherLatest } from "../weather/api";
import { indexLatest } from "./bands";

const REFRESH_MS = 5 * 60 * 1000; // slots arrive every 30 min; the API caches per slot

/** Sites (once), the latest traffic per leg and the latest weather per site (both refreshed). A failed traffic fetch leaves the legs grey, not the map blank; a failed weather fetch leaves the weather out. */
export function useTrafficData() {
  const [sites, setSites] = useState<Site[] | null>(null);
  const [rows, setRows] = useState<LatestLeg[]>([]);
  const [weather, setWeather] = useState<WeatherLatest[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getSites()
      .then((s) => !cancelled && setSites(s))
      .catch((e) => !cancelled && setError(String(e)));
    const loadLatest = () =>
      getLatestTraffic()
        .then((r) => !cancelled && setRows(r))
        .catch((e) => !cancelled && setError(String(e)));
    const loadWeather = () =>
      getWeatherLatest()
        .then((w) => !cancelled && setWeather(w))
        .catch(() => {}); // weather is secondary to traffic here: a failure only hides it
    const load = () => {
      loadLatest();
      loadWeather();
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const latest = useMemo(() => indexLatest(rows), [rows]);
  const weatherBySite = useMemo(() => new Map(weather.map((w) => [w.site_id, w])), [weather]);
  return { sites, latest, weatherBySite, error };
}
