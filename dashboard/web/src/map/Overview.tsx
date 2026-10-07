import { useCallback, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Page } from "../shell/AppShell";
import { BandIndicator } from "../theme/BandIndicator";
import { DemoMarker, DemoNote } from "../weather/DemoBadge";
import type { WeatherLatest } from "../weather/api";
import { LatestLeg } from "./api";
import { BASELINE_FULL, formatDelay, formatSlot, formatSpeed, legBand, legLabel } from "./bands";
import Legend from "./Legend";
import { SiteState, Summary, baselineDaysLeft, rankSites, summarize } from "./severity";
import TrafficMap from "./TrafficMap";
import { useTrafficData } from "./useTrafficData";
import "./Overview.css";

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

export function SiteRow({ state, latest, weather }: { state: SiteState; latest: Map<string, LatestLeg>; weather: WeatherLatest | undefined }) {
  const { site } = state;
  return (
    <li className="site-row" data-band={state.band}>
      <Link to={`/site/${site.site_id}`} className="site-row-link">
        <span className="site-row-head">
          <span className="site-name">{site.name}</span>
          <SiteWeatherCell now={weather} />
        </span>
        <span className="site-row-meta">{[site.city, site.road_name].filter(Boolean).join(" · ")}</span>
        <span className="site-legs">
          {site.legs.map((leg) => {
            const row = latest.get(leg.selected_route_id);
            return (
              <span key={leg.selected_route_id} className="site-leg">
                <span className="site-leg-name">{legLabel(leg.leg)}</span>
                <BandIndicator band={legBand(row).band} />
                <span className="site-leg-delay num">{formatDelay(row?.delay_s)}</span>
                <span className="site-leg-speed num">{formatSpeed(row?.speed_kmh)}</span>
              </span>
            );
          })}
        </span>
      </Link>
    </li>
  );
}

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

/** One page-level notice while any leg's baseline is still building, instead of a badge on every site. */
export function BaselineNotice({ samples }: { samples: number | null }) {
  if (samples === null || samples >= BASELINE_FULL) return null;
  const days = baselineDaysLeft(samples);
  return (
    <p className="baseline-notice">
      <strong>Baseline building</strong> ({samples} of {BASELINE_FULL} readings per leg). Legs are coloured by speed until the
      usual travel time is known{days > 0 ? `, in about ${days} day${days === 1 ? "" : "s"}` : ""}.
    </p>
  );
}

export default function Overview() {
  const { sites, latest, weatherBySite, error } = useTrafficData();
  const navigate = useNavigate();
  const select = useCallback((id: string) => navigate(`/site/${id}`), [navigate]);
  const ranked = useMemo(() => (sites ? rankSites(sites, latest) : []), [sites, latest]);
  const summary = useMemo(() => summarize(ranked, latest), [ranked, latest]);
  const anyDemoIcon = ranked.some((s) => weatherBySite.get(s.site.site_id)?.demo_icon_uri);

  return (
    <Page
      title="Overview"
      fill
      context={
        sites && (
          <>
            <NowSummary summary={summary} />
            <BaselineNotice samples={summary.baseline} />
          </>
        )
      }
    >
      {error && (
        <p className="overview-error" role="alert">
          Some data could not load: {error}
        </p>
      )}
      <div className="overview">
        <div className="map-frame">
          {sites ? <TrafficMap sites={sites} latest={latest} onSelectSite={select} /> : <div className="map-canvas map-placeholder" />}
          {sites && <Legend sites={sites} latest={latest} />}
        </div>
        <section className="site-list" aria-labelledby="site-list-title">
          <h2 id="site-list-title" className="site-list-title">
            Sites, worst first
          </h2>
          {!sites && !error && <p className="site-list-empty">Loading sites…</p>}
          <ol className="site-rows">
            {ranked.map((state) => (
              <SiteRow key={state.site.site_id} state={state} latest={latest} weather={weatherBySite.get(state.site.site_id)} />
            ))}
          </ol>
          {anyDemoIcon && <DemoNote>Weather icons come from Google's condition field, which only the demo source has.</DemoNote>}
        </section>
      </div>
    </Page>
  );
}
