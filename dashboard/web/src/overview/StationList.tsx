import { CSSProperties, ReactNode, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import type { LatestLeg, Site } from "../map/api";
import { formatDelay, formatSpeed, legBand, legContext, legLabel } from "../map/bands";
import { SiteState, siteState } from "../map/severity";
import "../site/Section.css"; // .skeleton
import { BandIndicator } from "../theme/BandIndicator";
import type { BandId } from "../theme/palette";
import { DemoMarker, DemoNote } from "../weather/DemoBadge";
import type { WeatherLatest } from "../weather/api";
import { RiskChip } from "./QueueRisk";
import {
  CONFIDENCE_LABELS,
  MapMode,
  Selection,
  StationRow,
  complaintsLine,
  reviewLine,
  topComplaintText,
  trafficLine,
} from "./model";
import "./StationList.css";

/** About the height of a loaded row, so the skeleton matches what loads into it. */
const SKELETON_ROW_HEIGHT = 168;
const SKELETON_ROWS = 4;

/** Core temperature, plus the condition icon (a demo-only field, so it carries the section's marker). */
export function SiteWeatherCell({ now }: { now: WeatherLatest | undefined }) {
  if (!now) return null;
  return (
    <span className="site-weather">
      {now.demo_icon_uri && (
        <span className="site-weather-icon">
          <img src={`${now.demo_icon_uri}.svg`} alt={now.demo_condition_text ?? "Weather condition"} />
          <DemoMarker />
        </span>
      )}
      <span className="num">{now.temperature_c == null ? "n/a" : `${now.temperature_c.toFixed(0)} °C`}</span>
    </span>
  );
}

/** Live conditions, small: the approach band (shape and name) and delay of the latest slot, and the weather. */
function LiveLine({ site, latest, weather }: { site: Site; latest: Map<string, LatestLeg>; weather: WeatherLatest | undefined }) {
  const leg = site.legs.find((l) => l.leg === "approach");
  const row = leg && latest.get(leg.selected_route_id);
  return (
    <span className="station-live">
      {leg && (
        <>
          <span className="station-live-label">Approach now</span>
          <BandIndicator band={legBand(row, legContext(site, leg.selected_route_id)).band} />
          {row && <span className="num">{formatDelay(row.delay_s)}</span>}
        </>
      )}
      <SiteWeatherCell now={weather} />
    </span>
  );
}

/** The way to the station page. */
function OpenStation({ siteId }: { siteId: string }) {
  return (
    <Link to={`/site/${encodeURIComponent(siteId)}`} className="station-open">
      Open station
    </Link>
  );
}

/** Shown when the row is selected: what the signals rest on, and the way to the station page. */
function StationDetails({ id, row, hidden }: { id: string; row: StationRow; hidden: boolean }) {
  const { site, risk, themes } = row;
  const confidence = risk?.confidence;
  return (
    <div className="station-details" id={id} hidden={hidden}>
      <dl>
        <div className="station-detail-text">
          <dt>Confidence</dt>
          <dd>
            {!risk
              ? "Unavailable"
              : confidence
                ? `${CONFIDENCE_LABELS[confidence.level]}. ${confidence.reason}. As of ${confidence.as_of}`
                : "Not assessed"}
          </dd>
        </div>
        {themes ? (
          <>
            <div>
              <dt>Road-queue reviews, last 12 months</dt>
              <dd className="num">{themes.road_queue_recent}</dd>
            </div>
            <div>
              <dt>Queue complaints, all sampled reviews</dt>
              <dd className="num">{themes.queue_complaints}</dd>
            </div>
            <div>
              <dt>Reviews labelled</dt>
              <dd className="num">{themes.n_labelled}</dd>
            </div>
          </>
        ) : (
          <div>
            <dt>Reviews</dt>
            <dd>Unavailable</dd>
          </div>
        )}
      </dl>
      <OpenStation siteId={site.site_id} />
    </div>
  );
}

/** Row frame shared by both modes: the toggle button with the name and city, and the details under it. */
function RowFrame({
  site,
  selected,
  onToggle,
  chip,
  children,
  details,
}: {
  site: Site;
  selected: boolean;
  onToggle: (siteId: string) => void;
  chip: ReactNode;
  children: ReactNode;
  details: (id: string) => ReactNode;
}) {
  const detailsId = `station-details-${site.site_id}`;
  return (
    <li className="station-row" data-site-id={site.site_id} data-selected={selected ? "" : undefined}>
      <button
        type="button"
        className="station-row-button"
        aria-expanded={selected}
        aria-controls={detailsId}
        onClick={() => onToggle(site.site_id)}
      >
        <span className="station-row-head">
          <span className="station-name">{site.name}</span>
          {chip}
        </span>
        {site.city && <span className="station-meta">{site.city}</span>}
        {children}
      </button>
      {details(detailsId)}
    </li>
  );
}

/** A "Queue risk" row. */
export function StationListRow({
  row,
  latest,
  weather,
  selected,
  showRisk,
  onToggle,
}: {
  row: StationRow;
  latest: Map<string, LatestLeg>;
  weather: WeatherLatest | undefined;
  selected: boolean;
  /** False when the traffic comparison failed to load, so no level can be given. */
  showRisk: boolean;
  onToggle: (siteId: string) => void;
}) {
  const { site, risk, themes } = row;
  const top = themes ? topComplaintText(themes.top) : null;
  return (
    <RowFrame
      site={site}
      selected={selected}
      onToggle={onToggle}
      chip={showRisk && <RiskChip risk={row.queueRisk} />}
      details={(id) => <StationDetails id={id} row={row} hidden={!selected} />}
    >
      <span className="station-lines">
        <span className="station-line" data-signal="traffic">
          {trafficLine(risk)}
        </span>
        <span className="station-line">{reviewLine(themes)}</span>
        {themes && <span className="station-line">{complaintsLine(themes)}</span>}
        {top && <span className="station-line">Top complaint: {top}</span>}
      </span>
      <LiveLine site={site} latest={latest} weather={weather} />
    </RowFrame>
  );
}

const NO_VALUE = "\u2014";

/** Band icon and name in a pill bordered in the band's colour, like the queue-risk chip. */
function BandChip({ band }: { band: BandId }) {
  return (
    <span className="band-chip" data-band={band}>
      <BandIndicator band={band} />
    </span>
  );
}

/** One leg's current reading: band, delay against free flow, times the usual travel time, speed. A missing value is a dash. */
function LegReading({ site, leg, latest }: { site: Site; leg: Site["legs"][number]; latest: Map<string, LatestLeg> }) {
  const row = latest.get(leg.selected_route_id);
  const { band } = legBand(row, legContext(site, leg.selected_route_id));
  const index = row?.congestion_index;
  return (
    <span className="station-line station-leg" data-leg={leg.leg}>
      <span className="station-live-label">{legLabel(leg.leg)}</span>
      <BandIndicator band={band} />
      <span className="num">{row?.delay_s == null ? NO_VALUE : formatDelay(row.delay_s)}</span>
      <span className="num">{index == null ? NO_VALUE : `${index.toFixed(1)}\u00d7`}</span>
      <span className="num">{row?.speed_kmh == null ? NO_VALUE : formatSpeed(row.speed_kmh)}</span>
    </span>
  );
}

/** A "Traffic now" row: the worse leg's band, a line per leg, and the weather. Core columns only; no queue-risk text. */
export function TrafficRow({
  state,
  latest,
  weather,
  selected,
  onToggle,
}: {
  state: SiteState;
  latest: Map<string, LatestLeg>;
  weather: WeatherLatest | undefined;
  selected: boolean;
  onToggle: (siteId: string) => void;
}) {
  const { site } = state;
  return (
    <RowFrame
      site={site}
      selected={selected}
      onToggle={onToggle}
      chip={<BandChip band={state.band} />}
      details={(id) => (
        <div className="station-details" id={id} hidden={!selected}>
          <OpenStation siteId={site.site_id} />
        </div>
      )}
    >
      <span className="station-lines">
        {site.legs.map((leg) => (
          <LegReading key={leg.selected_route_id} site={site} leg={leg} latest={latest} />
        ))}
      </span>
      {weather && (
        <span className="station-live">
          <SiteWeatherCell now={weather} />
        </span>
      )}
    </RowFrame>
  );
}

/** The station list beside the map. `rows` is null while the stations load. */
export function StationList({
  rows,
  latest,
  weatherBySite,
  heading,
  mode,
  selectedId,
  showRisk,
  windowDays,
  onToggle,
}: {
  rows: StationRow[] | null;
  latest: Map<string, LatestLeg>;
  weatherBySite: Map<string, WeatherLatest>;
  heading: string;
  mode: MapMode;
  selectedId: Selection;
  showRisk: boolean;
  /** Queue-risk window for the caption; null when it failed to load. */
  windowDays: number | null;
  onToggle: (siteId: string) => void;
}) {
  const listRef = useRef<HTMLOListElement>(null);
  const loaded = rows !== null;
  const anyDemoIcon = rows?.some((r) => weatherBySite.get(r.site.site_id)?.demo_icon_uri);
  // Bring the selected row into view (a marker click), only as far as needed: a visible row does not move.
  useEffect(() => {
    if (!selectedId || !loaded) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-site-id="${CSS.escape(selectedId)}"]`);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el?.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [selectedId, loaded]);

  return (
    <section className="site-list" aria-labelledby="site-list-title">
      <h2 id="site-list-title" className="site-list-title">
        {heading}
      </h2>
      {rows === null ? (
        <div className="station-skeleton" role="status" aria-label="Loading stations">
          {Array.from({ length: SKELETON_ROWS }, (_, i) => (
            <span
              key={i}
              className="skeleton"
              aria-hidden="true"
              style={{ "--skeleton-height": `${SKELETON_ROW_HEIGHT}px` } as CSSProperties}
            />
          ))}
        </div>
      ) : (
        <ol className="site-rows" ref={listRef}>
          {rows.map((row) =>
            mode === "now" ? (
              <TrafficRow
                key={row.site.site_id}
                state={siteState(row.site, latest)}
                latest={latest}
                weather={weatherBySite.get(row.site.site_id)}
                selected={row.site.site_id === selectedId}
                onToggle={onToggle}
              />
            ) : (
              <StationListRow
                key={row.site.site_id}
                row={row}
                latest={latest}
                weather={weatherBySite.get(row.site.site_id)}
                selected={row.site.site_id === selectedId}
                showRisk={showRisk}
                onToggle={onToggle}
              />
            ),
          )}
        </ol>
      )}
      {loaded && rows.length > 0 && mode === "risk" && (
        <p className="station-caption">
          {windowDays !== null && (
            <>Traffic: 500 m before and after each station, last {windowDays} days; not a count of cars. </>
          )}
          Reviews: at most 15 sampled per window.
        </p>
      )}
      {anyDemoIcon && <DemoNote>Weather icons come from Google's condition field, which only the demo source has.</DemoNote>}
    </section>
  );
}
