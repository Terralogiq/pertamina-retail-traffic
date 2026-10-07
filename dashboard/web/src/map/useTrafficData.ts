import { useEffect, useMemo, useState } from "react";
import { LatestLeg, Site, getLatestTraffic, getSites } from "./api";
import { indexLatest } from "./bands";

const REFRESH_MS = 5 * 60 * 1000; // slots arrive every 30 min; the API caches per slot

/** Sites (once) and the latest traffic per leg (refreshed). A failed traffic fetch leaves the legs grey, not the map blank. */
export function useTrafficData() {
  const [sites, setSites] = useState<Site[] | null>(null);
  const [rows, setRows] = useState<LatestLeg[]>([]);
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
    loadLatest();
    const timer = setInterval(loadLatest, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const latest = useMemo(() => indexLatest(rows), [rows]);
  return { sites, latest, error };
}
