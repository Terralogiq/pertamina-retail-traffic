import { FormEvent, useState } from "react";
import { login } from "../api";

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (await login(password)) {
        setPassword("");
        onSuccess();
      } else {
        setError("Wrong password");
      }
    } catch {
      setError("Login failed, try again");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ maxWidth: 320, margin: "20vh auto", display: "grid", gap: 12 }}>
      <h1>Pertamina SPBU traffic</h1>
      <input
        type="password"
        placeholder="Password"
        autoFocus
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button type="submit" disabled={busy || !password}>
        Sign in
      </button>
      {error && <div role="alert">{error}</div>}
    </form>
  );
}
