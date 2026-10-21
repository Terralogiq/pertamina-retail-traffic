import { useEffect, useState } from "react";
import { LatestLeg, Site, getLatestTraffic, getSites } from "../map/api";
import { PlacesResponse, getPlaces } from "../places/api";
import { AiSummary, getAiSummary } from "../summary/api";
import { WeatherLatest, getWeatherLatest } from "../weather/api";

/** `undefined` = still loading; `null` = loaded, nothing there; an Error = the request failed. */
export type Load<T> = T | null | undefined | Error;

export interface SiteData {
  site: Load<Site>;
  legs: Load<LatestLeg[]>;
  weather: Load<WeatherLatest>;
  places: Load<PlacesResponse>;
  summary: Load<AiSummary>;
}

const fail = (e: unknown) => (e instanceof Error ? e : new Error(String(e)));

/** The requests behind the site page; a parameter of `loadSiteData` so a test can count them. */
export const siteApi = { getSites, getLatestTraffic, getWeatherLatest, getPlaces, getAiSummary };

/**
 * Resolves the site from /api/sites first and only then starts the traffic, weather, Places and AI summary requests:
 * an unknown code (`/site/nope`) ends at `site = null` with no panel request. Each part reports on its own,
 * so a slow Places query doesn't hold back the traffic header.
 */
export async function loadSiteData(
  siteId: string,
  set: <K extends keyof SiteData>(key: K) => (v: SiteData[K]) => void,
  api: typeof siteApi = siteApi,
): Promise<void> {
  let site: Site | undefined;
  try {
    site = (await api.getSites()).find((s) => s.site_id === siteId);
  } catch (e) {
    set("site")(fail(e));
    return;
  }
  if (!site) {
    set("site")(null);
    return;
  }
  set("site")(site);
  api
    .getLatestTraffic()
    .then((rows) => set("legs")(rows.filter((r) => r.site_id === siteId)))
    .catch((e) => set("legs")(fail(e)));
  api
    .getWeatherLatest()
    .then((rows) => set("weather")(rows.find((w) => w.site_id === siteId) ?? null))
    .catch((e) => set("weather")(fail(e)));
  api
    .getPlaces(siteId)
    .then((d) => set("places")(d))
    .catch((e) => set("places")(fail(e)));
  // One request for the four section cards. The first view of a slot waits for generation, so it reports last.
  api
    .getAiSummary(siteId)
    .then((d) => set("summary")(d.summary))
    .catch((e) => set("summary")(fail(e)));
}

/** Everything the site header and panels share, fetched once (the panels used to refetch /api/sites each). */
export function useSiteData(siteId: string): SiteData {
  const [data, setData] = useState<{ siteId: string } & SiteData>({
    siteId,
    site: undefined,
    legs: undefined,
    weather: undefined,
    places: undefined,
    summary: undefined,
  });

  useEffect(() => {
    let live = true;
    const set =
      <K extends keyof SiteData>(key: K) =>
      (v: SiteData[K]) =>
        live && setData((d) => (d.siteId === siteId ? { ...d, [key]: v } : d));
    // Start from an empty record for this site, so the previous site's data never shows under the new heading.
    setData({ siteId, site: undefined, legs: undefined, weather: undefined, places: undefined, summary: undefined });
    void loadSiteData(siteId, set);
    return () => {
      live = false;
    };
  }, [siteId]);

// Until the effect has reset for a new siteId, report loading rather than the previous site's data.
  if (data.siteId !== siteId)
    return { site: undefined, legs: undefined, weather: undefined, places: undefined, summary: undefined };
  const { site, legs, weather, places, summary } = data;
  return { site, legs, weather, places, summary };
}

export const isReady = <T,>(v: Load<T>): v is T => v !== undefined && v !== null && !(v instanceof Error);
