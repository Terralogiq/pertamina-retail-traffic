import { useCallback, useEffect, useState } from "react";
import { Route, Routes, useParams } from "react-router-dom";
import { AppConfig, getConfig, setUnauthorizedHandler } from "./api";
import { Login } from "./login";
import { Overview, SiteMap } from "./map";
import { PlacesPanel } from "./places";
import { AppShell, Page } from "./shell/AppShell";
import { TrafficCharts } from "./traffic";
import { RainView, WeatherPanel } from "./weather";

function SiteDetail() {
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

export default function App() {
  // undefined = checking, null = not signed in
  const [config, setConfig] = useState<AppConfig | null | undefined>(undefined);

  const load = useCallback(() => {
    getConfig()
      .then(setConfig)
      .catch(() => {}); // a 401 already switched to the login form via the handler
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setConfig(null));
    load();
  }, [load]);

  if (config === undefined) return null;
  if (config === null) return <Login onSuccess={load} />;
  return (
    <AppShell>
      <Routes>
        <Route
          path="/"
          element={
            <Page title="Overview" fill>
              <Overview />
            </Page>
          }
        />
        <Route path="/site/:site_id" element={<SiteDetail />} />
        <Route
          path="/rain"
          element={
            <Page title="Traffic vs rain">
              <RainView />
            </Page>
          }
        />
      </Routes>
    </AppShell>
  );
}
