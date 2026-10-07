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
  const [data, setData] = useState<{ siteId: string } & SiteData>({
    siteId,
    site: undefined,
    legs: undefined,
    weather: undefined,
    places: undefined,
  });

  useEffect(() => {
    let live = true;
    const set =
      <K extends keyof SiteData>(key: K) =>
      (v: SiteData[K]) =>
        live && setData((d) => (d.siteId === siteId ? { ...d, [key]: v } : d));
    // Start from an empty record for this site, so the previous site's data never shows under the new heading.
    setData({ siteId, site: undefined, legs: undefined, weather: undefined, places: undefined });
    getSites()
      .then((all) => set("site")(all.find((s) => s.site_id === siteId) ?? null))
      .catch((e) => set("site")(fail(e)));
    getLatestTraffic()
      .then((rows) => set("legs")(rows.filter((r) => r.site_id === siteId)))
      .catch((e) => set("legs")(fail(e)));
    getWeatherLatest()
      .then((rows) => set("weather")(rows.find((w) => w.site_id === siteId) ?? null))
      .catch((e) => set("weather")(fail(e)));
    getPlaces(siteId)
      .then((d) => set("places")(d))
      .catch((e) => set("places")(fail(e)));
    return () => {
      live = false;
    };
  }, [siteId]);

  // Until the effect has reset for a new siteId, report loading rather than the previous site's data.
  if (data.siteId !== siteId) return { site: undefined, legs: undefined, weather: undefined, places: undefined };
  const { site, legs, weather, places } = data;
  return { site, legs, weather, places };
}

export const isReady = <T,>(v: Load<T>): v is T => v !== undefined && v !== null && !(v instanceof Error);
