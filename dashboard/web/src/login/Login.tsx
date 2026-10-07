import { FormEvent, useState } from "react";
import { login } from "../api";
import { usePageTitle } from "../shell/AppShell";
import { Wordmark } from "../theme/Wordmark";
import "./Login.css";

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  usePageTitle("Sign in");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!password) {
      setError("Enter the dashboard password.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (await login(password)) {
        setPassword("");
        onSuccess();
      } else {
        setError("That password isn't right. Check it and try again.");
      }
    } catch {
      setError("Couldn't reach the dashboard. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="login-card" onSubmit={submit} noValidate>
        <Wordmark />
        <h1 className="login-title">Sign in</h1>
        <p className="login-lede">Traffic, weather and site profiles for 10 SPBU, updated every 30 minutes.</p>
        {/* Password managers expect a username next to a password; the dashboard has one shared login. */}
        <input type="text" name="username" autoComplete="username" value="dashboard" readOnly hidden />
        <label className="login-label" htmlFor="login-password">
          Password
        </label>
        <input
          id="login-password"
          className="login-input"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={password}
          aria-invalid={error ? true : undefined}
          aria-describedby="login-error"
          onChange={(e) => setPassword(e.target.value)}
        />
        <p id="login-error" className="login-error" role="alert">
          {error}
        </p>
        <button type="submit" className="button button-primary login-submit" aria-busy={busy} disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
