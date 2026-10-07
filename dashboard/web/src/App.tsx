import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Route, Routes, useParams } from "react-router-dom";
import { importLibrary, setOptions } from "@googlemaps/js-api-loader";
import { AppConfig, getConfig, setUnauthorizedHandler } from "./api";
import { Login } from "./login";
import { TrafficCharts } from "./traffic";

// Placeholders: .4.2 (map), .4.3 (charts), .4.4 (weather), .4.5 (places) each add their routes here, one line each.

let mapsConfigured = false;

function Overview({ config }: { config: AppConfig }) {
  const el = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!mapsConfigured) {
      setOptions({ key: config.maps_browser_key, v: "weekly" });
      mapsConfigured = true;
    }
    importLibrary("maps")
      .then(({ Map }) => {
        // Centre of Indonesia; .4.2 fits the map to the 10 sites.
        new Map(el.current!, { center: { lat: -2.5, lng: 118 }, zoom: 5, mapTypeControl: false });
      })
      .catch((e) => setError(String(e)));
  }, [config.maps_browser_key]);

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <header style={{ padding: "8px 16px" }}>
        <strong>Pertamina SPBU traffic</strong> · overview
      </header>
      {error && <div role="alert">{error}</div>}
      <div ref={el} style={{ flex: 1 }} />
    </div>
  );
}

function SiteDetail() {
  const { site_id } = useParams();
  return (
    <div style={{ padding: 16 }}>
      <Link to="/">Overview</Link>
      <h1>Site {site_id}</h1>
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
      <Route path="/" element={<Overview config={config} />} />
      <Route path="/site/:site_id" element={<SiteDetail />} />
    </Routes>
  );
}
