import { useCallback, useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { AppConfig, getConfig, setUnauthorizedHandler, UnauthorizedError } from "./api";
import { Login } from "./login";
import { Overview } from "./map";
import { AppShell } from "./shell/AppShell";
import { PlacesVsTraffic } from "./places";
import { SiteDetail } from "./site";
import { Wordmark } from "./theme/Wordmark";
import { RainView } from "./weather";

export default function App() {
  // undefined = checking, null = not signed in
  const [config, setConfig] = useState<AppConfig | null | undefined>(undefined);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    getConfig()
      .then(setConfig)
      .catch((e) => {
        // a 401 already switched to the login form via the handler
        if (!(e instanceof UnauthorizedError)) setFailed(true);
      });
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setConfig(null));
    load();
  }, [load]);

  if (failed)
    return (
      <main className="login">
        <div className="login-card">
          <Wordmark />
          <h1 className="login-title">Couldn't load the dashboard</h1>
          <p className="login-lede" role="alert">Check your connection and try again.</p>
          <button type="button" className="button button-primary login-submit" onClick={load}>
            Try again
          </button>
        </div>
      </main>
    );
  if (config === undefined) return null;
  if (config === null) return <Login onSuccess={load} />;
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/site/:site_id" element={<SiteDetail />} />
        <Route path="/rain" element={<RainView />} />
        <Route path="/places" element={<PlacesVsTraffic />} />
      </Routes>
    </AppShell>
  );
}
