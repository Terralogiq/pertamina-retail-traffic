// Fetch client for /api. A 401 means the session cookie is missing or expired: notify the app (shows the login form).
export class UnauthorizedError extends Error {
  constructor() {
    super("unauthorized");
  }
}

let onUnauthorized: () => void = () => {};

export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin" });
  if (res.status === 401) {
    onUnauthorized();
    throw new UnauthorizedError();
  }
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

/** POST /api/login. Resolves true on success, false on a wrong password. */
export async function login(password: string): Promise<boolean> {
  const res = await fetch("/api/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (res.status === 401) return false;
  if (!res.ok) throw new Error(`/api/login: HTTP ${res.status}`);
  return true;
}

export interface AppConfig {
  maps_browser_key: string;
}

export const getConfig = () => getJson<AppConfig>("/api/config");
