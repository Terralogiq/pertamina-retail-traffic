// Site-local time: the UI shows WIB or WITA, never UTC (docs/plans/dashboard.md, Decisions: Time).
const LABELS: Record<string, string> = { "Asia/Jakarta": "WIB", "Asia/Makassar": "WITA", "Asia/Jayapura": "WIT" };

export const zoneLabel = (tz: string | undefined) => (tz && LABELS[tz]) || "UTC";

/** "14:30" in the site's time zone (UTC when unknown). */
export function localTime(iso: string, tz: string | undefined): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: tz && LABELS[tz] ? tz : "UTC",
  }).format(new Date(iso));
}
