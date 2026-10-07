import TrafficMap from "./TrafficMap";
import { useTrafficData } from "./useTrafficData";
import "./Overview.css";

/** Map zoomed to one site's legs, coloured like the overview. */
export default function SiteMap({ siteId }: { siteId: string }) {
  const { sites, latest, error } = useTrafficData();
  const site = sites?.find((s) => s.site_id === siteId);
  return (
    <div className="site-map">
      {error && (
        <p className="overview-error" role="alert">
          The map data couldn't load. {error}
        </p>
      )}
      {sites && !site && (
        <p className="overview-error" role="alert">
          Unknown site {siteId}.
        </p>
      )}
      <div className="map-frame site-map-frame">
        {sites && site ? <TrafficMap sites={sites} latest={latest} siteId={siteId} /> : <div className="map-canvas map-placeholder" />}
      </div>
    </div>
  );
}
