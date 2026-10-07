import { useParams } from "react-router-dom";
import { SiteMap } from "../map";
import { PlacesPanel } from "../places";
import { Page } from "../shell/AppShell";
import { TrafficCharts } from "../traffic";
import { WeatherPanel } from "../weather";

export function SiteDetail() {
  const { site_id } = useParams();
  return (
    <Page title={`Site ${site_id}`}>
      <SiteMap siteId={site_id!} />
      <TrafficCharts siteId={site_id} />
      <WeatherPanel siteId={site_id!} />
      <PlacesPanel siteId={site_id!} />
    </Page>
  );
}
