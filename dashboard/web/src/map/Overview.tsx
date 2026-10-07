import { useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LatestLeg, Site } from "./api";
import { baselineBadge, baselineProgress, formatDelay, formatSlot, legColor, legLabel, siteLatest } from "./bands";
import Legend from "./Legend";
import TrafficMap from "./TrafficMap";
import { useTrafficData } from "./useTrafficData";

function SiteListItem({ site, latest }: { site: Site; latest: Map<string, LatestLeg> }) {
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
          <span style={{ fontSize: 12, background: "#fff3cd", border: "1px solid #e0c36a", borderRadius: 4, padding: "0 4px" }}>
            {badge}
          </span>
        )}
        {/* Weather (icon + temperature) goes here: .4.4. */}
      </Link>
    </li>
  );
}

export default function Overview() {
  const { sites, latest, error } = useTrafficData();
  const navigate = useNavigate();
  const select = useCallback((id: string) => navigate(`/site/${id}`), [navigate]);

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <header style={{ padding: "8px 16px" }}>
        <strong>Pertamina SPBU traffic</strong> · overview
      </header>
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
            {sites?.map((site) => <SiteListItem key={site.site_id} site={site} latest={latest} />)}
          </ul>
        </aside>
      </div>
    </div>
  );
}
