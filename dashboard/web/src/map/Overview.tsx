import { useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Page } from "../shell/AppShell";
import { LatestLeg, Site } from "./api";
import { baselineBadge, baselineProgress, formatDelay, formatSlot, legColor, legLabel, siteLatest } from "./bands";
import Legend from "./Legend";
import TrafficMap from "./TrafficMap";
import { useTrafficData } from "./useTrafficData";
import { WeatherLatest } from "../weather/api";
import { SiteWeather } from "../weather/SiteWeather";

function SiteListItem({ site, latest, weather }: { site: Site; latest: Map<string, LatestLeg>; weather: WeatherLatest | undefined }) {
  const rows = siteLatest(site, latest);
  const badge = baselineBadge(baselineProgress(rows));
  return (
    <li style={{ padding: "8px 12px", borderBottom: "1px solid #ddd" }}>
      <Link to={`/site/${site.site_id}`} style={{ color: "inherit", textDecoration: "none" }}>
        <div style={{ fontSize: 12, color: "#555" }}>{site.city}</div>
        <strong>{site.name}</strong>
        {site.legs.map((leg) => {
          const row = latest.get(leg.selected_route_id);
          return (
            <div key={leg.selected_route_id} style={{ fontSize: 13 }}>
              <span style={{ color: legColor(row).color }}>&#9632;</span> {legLabel(leg.leg)} {formatDelay(row?.delay_s)}
            </div>
          );
        })}
        {rows.length > 0 && (
          <div style={{ fontSize: 12, color: "#555" }}>slot {formatSlot(rows[0].slot_time, site.timezone)}</div>
        )}
        {badge && (
          <span
            style={{
              fontSize: 12,
              background: "var(--state-warning-surface)",
              border: "1px solid var(--state-warning-border)",
              borderRadius: 4,
              padding: "0 4px",
            }}
          >
            {badge}
          </span>
        )}
        <SiteWeather now={weather} />
      </Link>
    </li>
  );
}

export default function Overview() {
  const { sites, latest, weatherBySite, error } = useTrafficData();
  const navigate = useNavigate();
  const select = useCallback((id: string) => navigate(`/site/${id}`), [navigate]);

  return (
    <Page title="Overview" fill>
      <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
        {error && <div role="alert">{error}</div>}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <div style={{ flex: 1, minHeight: 0 }}>
              {sites && <TrafficMap sites={sites} latest={latest} onSelectSite={select} />}
            </div>
            {sites && <Legend sites={sites} latest={latest} />}
          </div>
          <aside style={{ width: 300, overflowY: "auto", borderLeft: "1px solid #ddd" }}>
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {sites?.map((site) => <SiteListItem key={site.site_id} site={site} latest={latest} weather={weatherBySite.get(site.site_id)} />)}
            </ul>
          </aside>
        </div>
      </div>
    </Page>
  );
}
