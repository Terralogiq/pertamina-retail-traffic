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

/** A failed /api call. `message` is written for the reader (problem + recovery); `path` and `status` are for debugging. */
export class ApiError extends Error {
  constructor(readonly path: string, readonly status: number | null) {
    super(
      status === null
        ? "No connection to the dashboard server. Check your connection and reload the page."
        : status >= 500
          ? `The server had a problem (HTTP ${status}). Try again in a minute.`
          : `The request failed (HTTP ${status}). Reload the page.`,
    );
  }
}

/** Reader-facing text for any caught error: the message alone, without "Error:" or a request URL. */
export const errorText = (e: unknown): string => (e instanceof Error ? e.message : String(e));

export async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { credentials: "same-origin" });
  } catch {
    throw new ApiError(path, null);
  }
  if (res.status === 401) {
    onUnauthorized();
    throw new UnauthorizedError();
  }
  if (!res.ok) throw new ApiError(path, res.status);
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
