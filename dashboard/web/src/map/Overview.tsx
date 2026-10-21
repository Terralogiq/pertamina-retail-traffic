import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { Link } from "react-router-dom";
import { StationList } from "../overview/StationList";
import {
  MapMode,
  Selection,
  SelectionAction,
  StationRow,
  buildRows,
  effectiveMode,
  RISK_GUIDANCE,
  orderByRank,
  orderByRisk,
  riskSummary,
  selectionReducer,
} from "../overview/model";
import { StationData, useStationData } from "../overview/useStationData";
import { Page } from "../shell/AppShell";
import { Notice } from "../site/Section";
import { isReady } from "../site/useSiteData";
import type { WeatherLatest } from "../weather/api";
import { LatestLeg, Site } from "./api";
import { BASELINE_FULL, formatDelay, formatSlot, legLabel } from "./bands";
import { Summary, guardBusyRank, rankSites, summarize } from "./severity";
import { Segmented } from "./Segmented";
import TrafficMap from "./TrafficMap";
import { useTrafficData } from "./useTrafficData";
import "./Overview.css";

/** The "now" line under the page title: how many sites are slowed, the worst one, and the slot it reflects. */
export function NowSummary({ summary }: { summary: Summary }) {
  if (summary.reporting === 0) return <p className="now-line">Waiting for the first traffic readings.</p>;
  const { worst } = summary;
  return (
    <p className="now-line">
      <span>
        <strong className="num">
          {summary.slowed} of {summary.total}
        </strong>{" "}
        sites slowed
      </span>
      {worst && worst.worstDelay !== null && worst.worstDelay > 0 && (
        <span>
          Worst:{" "}
          <Link to={`/site/${worst.site.site_id}`}>{worst.site.name}</Link>, {worst.worstLeg ? legLabel(worst.worstLeg).toLowerCase() : ""}{" "}
          <strong className="num">{formatDelay(worst.worstDelay)}</strong>
        </span>
      )}
      {summary.slotTime && <span className="now-slot">Reading of {formatSlot(summary.slotTime, "Asia/Jakarta")}</span>}
    </p>
  );
}

/** The "Queue risk" line under the page title: stations per level, the fixed guidance caption, and the windows the two signals cover. */
export function RiskSummary({ rows, windowDays }: { rows: StationRow[] | null; windowDays: number | null }) {
  if (rows === null) return <p className="now-line">Loading stations…</p>;
  return (
    <p className="now-line">
      <strong className="num">{riskSummary(rows)}</strong>
      <span className="now-slot">{RISK_GUIDANCE}</span>
      {windowDays !== null && <span className="now-slot">Traffic from the last {windowDays} days, reviews from the last 12 months</span>}
    </p>
  );
}

/** One page-level notice while any leg's baseline is still building, instead of a badge on every site. */
export function BaselineNotice({ samples }: { samples: number | null }) {
  if (samples === null || samples >= BASELINE_FULL) return null;
  return (
    <p className="baseline-notice">
      <strong>Provisional</strong> ({samples} of {BASELINE_FULL} readings per leg). The usual travel time is not ready yet.
    </p>
  );
}

const MODES: { value: MapMode; label: string }[] = [
  { value: "risk", label: "Queue risk" },
  { value: "now", label: "Traffic now" },
];

const HEADINGS: Record<MapMode, string> = {
  risk: "Stations, highest queue risk first",
  now: "Stations, worst traffic first",
};

export interface OverviewViewProps {
  sites: Site[] | null;
  latest: Map<string, LatestLeg>;
  weatherBySite: Map<string, WeatherLatest>;
  /** Live traffic or site list failure. */
  error: string;
  station: StationData;
  /** The mode picked in the toggle; the page shows "Traffic now" whatever it is when queue risk failed. */
  mode: MapMode;
  onMode: (m: MapMode) => void;
  selected: Selection;
  dispatch: (a: SelectionAction) => void;
}

/** The overview for given data and state, apart from fetching, so a test can render every state. */
export function OverviewView({ sites, latest, weatherBySite, error, station, mode: chosen, onMode, selected, dispatch }: OverviewViewProps) {
  const riskFailed = station.risk instanceof Error;
  const themesFailed = station.themes instanceof Error;
  const risk = isReady(station.risk) ? station.risk : null;
  const themes = isReady(station.themes) ? station.themes : null;
  const mode = effectiveMode(chosen, station.risk);
  // Current-state order. Busy-hour delay is not a sort key until a site profile is ready.
  const ranked = useMemo(
    () => (sites ? guardBusyRank(rankSites(sites, latest), false, () => null) : []),
    [sites, latest],
  );
  const summary = useMemo(() => summarize(ranked, latest), [ranked, latest]);
  const settled = sites !== null && station.risk !== undefined && station.themes !== undefined;
  const rows = useMemo(
    () => (settled && sites ? buildRows(sites, risk?.sites ?? null, themes?.sites ?? null) : null),
    [settled, sites, risk, themes],
  );
  const listed = useMemo(() => rows && (mode === "risk" ? orderByRisk(rows) : orderByRank(rows, ranked)), [rows, mode, ranked]);
  const queueRisks = useMemo(
    () => (mode === "now" ? undefined : rows ? new Map(rows.map((r) => [r.site.site_id, r.queueRisk])) : null),
    [mode, rows],
  );
  const selectSite = useCallback((siteId: string) => dispatch({ type: "select", siteId }), [dispatch]);
  const toggleSite = useCallback((siteId: string) => dispatch({ type: "toggle", siteId }), [dispatch]);
  const windowDays = risk?.window_days ?? null;

  return (
    <Page
      title="Overview"
      fullWidth
      actions={!riskFailed && <Segmented label="Map and list show" options={MODES} value={mode} onChange={onMode} />}
      context={
        sites && (
          <>
            {mode === "risk" ? <RiskSummary rows={rows} windowDays={windowDays} /> : <NowSummary summary={summary} />}
            <BaselineNotice samples={summary.baseline} />
          </>
        )
      }
    >
      {error && (
        <p className="overview-error" role="alert">
          Some data couldn't load. {error}
        </p>
      )}
      {(riskFailed || themesFailed) && (
        <div className="overview-notices">
          {station.risk instanceof Error && (
            <Notice tone="error">Couldn't load the slowdown comparison, so the map shows traffic now. {station.risk.message}</Notice>
          )}
          {station.themes instanceof Error && (
            <Notice tone="error">Couldn't load review counts, so queue risk comes from traffic only. {station.themes.message}</Notice>
          )}
        </div>
      )}
      <div className="overview">
        <div className="map-frame">
          {sites ? (
            <TrafficMap sites={sites} latest={latest} onSelectSite={selectSite} queueRisks={queueRisks} selectedId={selected} />
          ) : (
            <div className="map-canvas map-placeholder" />
          )}
        </div>
        <StationList
          rows={!sites && error ? [] : listed}
          latest={latest}
          weatherBySite={weatherBySite}
          heading={HEADINGS[mode]}
          mode={mode}
          selectedId={selected}
          showRisk={!riskFailed}
          windowDays={windowDays}
          onToggle={toggleSite}
        />
      </div>
    </Page>
  );
}

export default function Overview() {
  const { sites, latest, weatherBySite, error } = useTrafficData();
  const station = useStationData();
  const [mode, setMode] = useState<MapMode>("risk");
  const [selected, dispatch] = useReducer(selectionReducer, null);
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && dispatch({ type: "clear" });
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected]);
  return (
    <OverviewView
      sites={sites}
      latest={latest}
      weatherBySite={weatherBySite}
      error={error}
      station={station}
      mode={mode}
      onMode={setMode}
      selected={selected}
      dispatch={dispatch}
    />
  );
}
