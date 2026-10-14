import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Site } from "../map/api";
import { Segmented } from "../map/Segmented";
import { Notice, Skeleton } from "../site/Section";
import { Load } from "../site/useSiteData";
import { QueueRiskResponse, StationThemesResponse, getQueueRisk, getStationThemes } from "./api";
import {
  CONFIDENCE_LABELS,
  STATION_SORTS,
  StationRow,
  StationSort,
  TIER_LABELS,
  buildRows,
  sortRows,
  tierDetail,
  topComplaintText,
} from "./model";
import "./StationTable.css";

/** Height of the loaded table (10 rows), so the skeleton matches what loads into it. */
const TABLE_HEIGHT = 560;

const DASH = "—";

export interface StationData {
  risk: Load<QueueRiskResponse>;
  themes: Load<StationThemesResponse>;
}

const fail = (e: unknown) => (e instanceof Error ? e : new Error(String(e)));

/** The two requests behind the table; a parameter of `loadStationData` so a test can mock them. */
export const stationApi = { getQueueRisk, getStationThemes };

/** Starts both requests; each reports on its own, so one failing leaves the other's columns intact. */
export function loadStationData(
  set: <K extends keyof StationData>(key: K) => (v: StationData[K]) => void,
  api: typeof stationApi = stationApi,
): Promise<void> {
  return Promise.allSettled([
    api.getQueueRisk().then(set("risk"), (e) => set("risk")(fail(e))),
    api.getStationThemes().then(set("themes"), (e) => set("themes")(fail(e))),
  ]).then(() => undefined);
}

function useStationData(): StationData {
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

const payload = <T,>(v: Load<T>): T | null => (v === undefined || v === null || v instanceof Error ? null : v);

function RiskCells({ row }: { row: StationRow }) {
  const { risk } = row;
  if (!risk) {
    return (
      <>
        <td>{DASH}</td>
        <td>{DASH}</td>
      </>
    );
  }
  const detail = tierDetail(risk);
  const { confidence } = risk;
  return (
    <>
      <td>
        <span className="station-tier" data-tier={risk.tier}>
          {TIER_LABELS[risk.tier]}
        </span>
        {detail && <span className="station-sub">{detail}</span>}
      </td>
      <td>
        {confidence ? (
          <>
            <span className="station-level">{CONFIDENCE_LABELS[confidence.level]}</span>
            <span className="station-sub">{confidence.reason}</span>
            <span className="station-sub station-asof">as of {confidence.as_of}</span>
          </>
        ) : (
          DASH
        )}
      </td>
    </>
  );
}

function ThemeCells({ row }: { row: StationRow }) {
  const { themes } = row;
  if (!themes) {
    return (
      <>
        <td className="num station-count">{DASH}</td>
        <td>{DASH}</td>
        <td className="num station-count">{DASH}</td>
      </>
    );
  }
  return (
    <>
      <td className="num station-count">{themes.queue_complaints}</td>
      <td>{topComplaintText(themes.top) ?? DASH}</td>
      <td className="num station-count">{themes.n_labelled}</td>
    </>
  );
}

/** The table for loaded (or failed) data. A failed endpoint leaves its columns as dashes and says so above the table. */
export function StationTableView({
  sites,
  data,
  sort,
  onSort,
}: {
  sites: Site[] | null;
  data: StationData;
  sort: StationSort;
  onSort: (s: StationSort) => void;
}) {
  const risk = payload(data.risk);
  const themes = payload(data.themes);
  const rows = useMemo(
    () => sortRows(buildRows(sites ?? [], risk?.sites ?? null, themes?.sites ?? null), sort),
    [sites, risk, themes, sort],
  );
  const loading = sites === null || data.risk === undefined || data.themes === undefined;
  return (
    <section className="station-table-section" aria-labelledby="stations-title">
      <div className="station-table-head">
        <h2 id="stations-title">Stations at a glance</h2>
        <Segmented label="Sort stations" options={STATION_SORTS} value={sort} onChange={onSort} />
      </div>
      {loading && <Skeleton height={TABLE_HEIGHT} label="Loading stations" />}
      {!loading && data.risk instanceof Error && (
        <Notice tone="error">Couldn't load the slowdown comparison, so that column is blank. {data.risk.message}</Notice>
      )}
      {!loading && data.themes instanceof Error && (
        <Notice tone="error">Couldn't load review counts, so the complaint columns are blank. {data.themes.message}</Notice>
      )}
      {!loading && (
        <div className="station-table-scroll" role="region" aria-label="Stations at a glance, scrollable" tabIndex={0}>
          <table className="station-table" aria-labelledby="stations-title">
            <thead>
              <tr>
                <th scope="col" aria-sort={sort === "name" ? "ascending" : undefined}>
                  Station
                </th>
                <th scope="col" aria-sort={sort === "risk" ? "other" : undefined}>
                  Slower before than after
                </th>
                <th scope="col">Confidence</th>
                <th scope="col" className="station-count" aria-sort={sort === "complaints" ? "descending" : undefined}>
                  Queue complaints
                </th>
                <th scope="col" aria-sort={sort === "top" ? "descending" : undefined}>
                  Top complaint
                </th>
                <th scope="col" className="station-count">
                  Reviews labelled
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.site.site_id}>
                  <th scope="row">
                    <Link to={`/site/${encodeURIComponent(row.site.site_id)}`}>{row.site.name}</Link>
                    {row.site.city && <span className="station-sub">{row.site.city}</span>}
                  </th>
                  <RiskCells row={row} />
                  <ThemeCells row={row} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!loading && (
        <div className="station-captions">
          {risk && (
            <p>
              Road traffic on the 500 m before and after each station, from the last {risk.window_days} days. Not a count of
              cars at the pumps, and not checked on the ground.
            </p>
          )}
          <p>Complaints come from a sample of at most 15 Google reviews per window and station. Counts, not rates.</p>
        </div>
      )}
    </section>
  );
}

/** "Stations at a glance": queue risk and review complaints for every station, from two all-site endpoints. */
export function StationTable({ sites }: { sites: Site[] | null }) {
  const data = useStationData();
  const [sort, setSort] = useState<StationSort>("name");
  return <StationTableView sites={sites} data={data} sort={sort} onSort={setSort} />;
}
