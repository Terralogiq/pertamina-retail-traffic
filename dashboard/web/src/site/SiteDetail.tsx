import { Link, useParams } from "react-router-dom";
import type { LatestLeg, Site } from "../map/api";
import { BASELINE_FULL, baselineProgress } from "../map/bands";
import { SiteMap } from "../map";
import { PlacesPanel } from "../places";
import { Page } from "../shell/AppShell";
import { BandIndicator } from "../theme/BandIndicator";
import { TrafficCharts, TrafficPattern } from "../traffic";
import { formatDelay, legLabel, tzLabel } from "../traffic/model";
import { WeatherPanel } from "../weather";
import type { WeatherLatest } from "../weather/api";
import type { PlacesResponse } from "../places/api";
import { Section } from "./Section";
import { legBand } from "./legBand";
import { Load, isReady, useSiteData } from "./useSiteData";
import "./SiteDetail.css";

const SECTIONS = [
  { id: "traffic", label: "Traffic" },
  { id: "pattern", label: "Weekly pattern" },
  { id: "weather", label: "Weather" },
  { id: "places", label: "Places" },
];

/** "SPBU 24.351.34 · Bandar Lampung · Jl. P. Antasari · WIB": the ID stays secondary to the name (F4). */
export function siteContext(site: Site): string {
  return [`SPBU ${site.site_id}`, site.city, site.road_name, tzLabel(site.timezone)].filter(Boolean).join(" · ");
}

/** "Congestion is provisional: baseline 27 of 302 samples" while any leg's baseline is building, else null. */
export function baselineNotice(legs: LatestLeg[]): string | null {
  const n = baselineProgress(legs);
  return n !== null && n < BASELINE_FULL
    ? `Baseline building: ${n} of ${BASELINE_FULL} samples. Leg status uses speed until the baseline is full; the congestion index is provisional.`
    : null;
}

/** Status line under the heading: each leg's latest delay and band, the weather now and the rating (F4). */
export function StatusStrip({
  legs,
  weather,
  places,
}: {
  legs: Load<LatestLeg[]>;
  weather: Load<WeatherLatest>;
  places: Load<PlacesResponse>;
}) {
  const rating = isReady(places) ? places.details?.rating : null;
  return (
    <dl className="status-strip" aria-label="Current status">
      {legs === undefined && <div className="status-item status-item-loading" aria-busy="true" />}
      {isReady(legs) &&
        (legs.length === 0 ? (
          <div className="status-item">
            <dt>Traffic</dt>
            <dd>No reading in the last 2 hours</dd>
          </div>
        ) : (
          [...legs]
            .sort((a, b) => a.leg.localeCompare(b.leg))
            .map((leg) => {
              const { band, basis } = legBand(leg);
              return (
                <div className="status-item" key={leg.selected_route_id}>
                  <dt>{legLabel(leg.leg)}</dt>
                  <dd>
                    <span className="status-value num">{formatDelay(leg.delay_s)}</span>
                    <BandIndicator band={band} />
                    {basis === "speed" && leg.speed_kmh != null && (
                      <span className="status-sub num">{Math.round(leg.speed_kmh)} km/h</span>
                    )}
                  </dd>
                </div>
              );
            })
        ))}
      {isReady(weather) && (
        <div className="status-item">
          <dt>Weather now</dt>
          <dd>
            <span className="status-value num">
              {weather.temperature_c == null ? "n/a" : `${weather.temperature_c.toFixed(1)} °C`}
            </span>
            <span className="status-sub">{weather.rain_flag ? "raining" : weather.rain_flag === false ? "no rain" : ""}</span>
          </dd>
        </div>
      )}
      {rating != null && (
        <div className="status-item">
          <dt>Google rating</dt>
          <dd>
            <span className="status-value num">{rating.toFixed(1)}</span>
            <span className="status-sub">of 5</span>
          </dd>
        </div>
      )}
    </dl>
  );
}

function SiteNav() {
  return (
    <nav className="site-nav" aria-label="Sections">
      {SECTIONS.map((s) => (
        <a key={s.id} href={`#${s.id}`}>
          {s.label}
        </a>
      ))}
    </nav>
  );
}

export function SiteDetail() {
  const { site_id } = useParams();
  const siteId = site_id!;
  const { site, legs, weather, places } = useSiteData(siteId);
  const timezone = isReady(site) ? site.timezone : site === undefined ? undefined : null;
  const notice = isReady(legs) ? baselineNotice(legs) : null;

  if (site === null) {
    return (
      <Page title="Unknown site" context={`No SPBU with code ${siteId}`}>
        <Link to="/">Back to the overview</Link>
      </Page>
    );
  }

  // Until /api/sites answers, the route code stands in for the name (pinned by shell/AppShell.test.tsx).
  const title = isReady(site) ? site.name : `Site ${siteId}`;
  return (
    <Page
      title={title}
      context={
        <div className="site-context">
          {isReady(site) && <p>{siteContext(site)}</p>}
          {site instanceof Error && <p role="alert">Couldn't load the site: {site.message}</p>}
          <StatusStrip legs={legs} weather={weather} places={places} />
        </div>
      }
      actions={<SiteNav />}
    >
      <div className="page-grid site-grid">
        <div className="span-8 site-column">
          <Section id="map" title="Road segments" note="Approach and departure legs on the SPBU side, coloured by current state">
            <SiteMap siteId={siteId} />
          </Section>
          <TrafficCharts siteId={siteId} timezone={timezone} baselineNote={notice} />
          <TrafficPattern siteId={siteId} timezone={timezone} />
        </div>
        <div className="span-4 site-column">
          <WeatherPanel siteId={siteId} timezone={timezone} now={weather} />
          <PlacesPanel data={places} />
        </div>
      </div>
    </Page>
  );
}
