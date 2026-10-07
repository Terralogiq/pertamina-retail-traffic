import Legend from "./Legend";
import TrafficMap from "./TrafficMap";
import { useTrafficData } from "./useTrafficData";

/** Map zoomed to one site's legs, coloured like the overview. */
export default function SiteMap({ siteId }: { siteId: string }) {
  const { sites, latest, error } = useTrafficData();
  const known = sites?.some((s) => s.site_id === siteId);
  return (
    <div>
      {error && <div role="alert">{error}</div>}
      {sites && !known && <div role="alert">Unknown site {siteId}</div>}
      <div style={{ height: 360 }}>{sites && known && <TrafficMap sites={sites} latest={latest} siteId={siteId} />}</div>
      {sites && known && <Legend sites={sites.filter((s) => s.site_id === siteId)} latest={latest} />}
    </div>
  );
}
