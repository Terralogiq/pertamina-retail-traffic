import { useEffect, useState } from "react";
import { LatestLeg, Site, getLatestTraffic, getSites } from "../map/api";
import { PlacesResponse, getPlaces } from "../places/api";
import { WeatherLatest, getWeatherLatest } from "../weather/api";

/** `undefined` = still loading; `null` = loaded, nothing there; an Error = the request failed. */
export type Load<T> = T | null | undefined | Error;

export interface SiteData {
  site: Load<Site>;
  legs: Load<LatestLeg[]>;
  weather: Load<WeatherLatest>;
  places: Load<PlacesResponse>;
}

const fail = (e: unknown) => (e instanceof Error ? e : new Error(String(e)));

/**
 * Everything the site header and panels share, fetched once and in parallel (the panels used to refetch
 * /api/sites each). Each part resolves on its own, so a slow Places query doesn't hold back the traffic header.
 */
export function useSiteData(siteId: string): SiteData {
  const [site, setSite] = useState<Load<Site>>(undefined);
  const [legs, setLegs] = useState<Load<LatestLeg[]>>(undefined);
  const [weather, setWeather] = useState<Load<WeatherLatest>>(undefined);
  const [places, setPlaces] = useState<Load<PlacesResponse>>(undefined);

  useEffect(() => {
    let live = true;
    const set = <T,>(setter: (v: Load<T>) => void) => (v: Load<T>) => live && setter(v);
    setSite(undefined);
    setLegs(undefined);
    setWeather(undefined);
    setPlaces(undefined);
    getSites()
      .then((all) => set(setSite)(all.find((s) => s.site_id === siteId) ?? null))
      .catch((e) => set(setSite)(fail(e)));
    getLatestTraffic()
      .then((rows) => set(setLegs)(rows.filter((r) => r.site_id === siteId)))
      .catch((e) => set(setLegs)(fail(e)));
    getWeatherLatest()
      .then((rows) => set(setWeather)(rows.find((w) => w.site_id === siteId) ?? null))
      .catch((e) => set(setWeather)(fail(e)));
    getPlaces(siteId)
      .then((d) => set(setPlaces)(d))
      .catch((e) => set(setPlaces)(fail(e)));
    return () => {
      live = false;
    };
  }, [siteId]);

  return { site, legs, weather, places };
}

export const isReady = <T,>(v: Load<T>): v is T => v !== undefined && v !== null && !(v instanceof Error);
