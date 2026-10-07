import { useCallback, useEffect, useState } from "react";
import { Link, Route, Routes, useParams } from "react-router-dom";
import { AppConfig, getConfig, setUnauthorizedHandler } from "./api";
import { Login } from "./login";
import { Overview, SiteMap } from "./map";
import { TrafficCharts } from "./traffic";

// Placeholders: .4.2 (map), .4.3 (charts), .4.4 (weather), .4.5 (places) each add their routes here, one line each.

function SiteDetail() {
  const { site_id } = useParams();
  return (
    <div style={{ padding: 16 }}>
      <Link to="/">Overview</Link>
      <h1>Site {site_id}</h1>
      <div>
        <SiteMap siteId={site_id!} />
      </div>
      <TrafficCharts siteId={site_id} />
    </div>
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
    <Routes>
      <Route path="/" element={<Overview />} />
      <Route path="/site/:site_id" element={<SiteDetail />} />
    </Routes>
  );
}
