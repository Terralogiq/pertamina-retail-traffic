import { useEffect, useState } from "react";
import type { Load } from "../site/useSiteData";
import { QueueRiskResponse, StationThemesResponse, getQueueRisk, getStationThemes } from "./api";

export interface StationData {
  risk: Load<QueueRiskResponse>;
  themes: Load<StationThemesResponse>;
}

const fail = (e: unknown) => (e instanceof Error ? e : new Error(String(e)));

/** The two requests behind the station list; a parameter of `loadStationData` so a test can mock them. */
export const stationApi = { getQueueRisk, getStationThemes };

/** Starts both requests; each reports on its own, so one failing leaves the other's signal intact. */
export function loadStationData(
  set: <K extends keyof StationData>(key: K) => (v: StationData[K]) => void,
  api: typeof stationApi = stationApi,
): Promise<void> {
  return Promise.allSettled([
    api.getQueueRisk().then(set("risk"), (e) => set("risk")(fail(e))),
    api.getStationThemes().then(set("themes"), (e) => set("themes")(fail(e))),
  ]).then(() => undefined);
}

/** Queue risk and review themes for every station, loaded once; each is undefined while loading and an Error when it failed. */
export function useStationData(): StationData {
  const [data, setData] = useState<StationData>({ risk: undefined, themes: undefined });
  useEffect(() => {
    let live = true;
    const set =
      <K extends keyof StationData>(key: K) =>
      (v: StationData[K]) =>
        live && setData((d) => ({ ...d, [key]: v }));
    void loadStationData(set);
    return () => {
      live = false;
    };
  }, []);
  return data;
}
