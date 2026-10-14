// Pure helpers behind the overview station table: labels, the joined rows and the sort orders.
import type { Site } from "../map/api";
import { formatDelay } from "../map/bands";
import { categoryName } from "../reviews/model";
import type { ConfidenceLevel, QueueRiskSite, StationThemes, Tier } from "./api";

export const TIER_LABELS: Record<Tier, string> = {
  strong: "Strong",
  moderate: "Moderate",
  weak: "Weak",
  none: "None",
  cannot_tell: "Cannot tell",
};

export const CONFIDENCE_LABELS: Record<ConfidenceLevel, string> = {
  medium: "Medium",
  low: "Low",
  very_low: "Very low",
  none: "None",
};

export const CANNOT_TELL_TEXT = "Road past the station is as slow, so this can't be seen";

/** "on 12 of 14 days, usually +1.5 min"; empty for tiers that have no days to count (none, cannot tell). */
export function tierDetail(r: QueueRiskSite): string {
  if (r.tier === "cannot_tell") return CANNOT_TELL_TEXT;
  if (r.tier === "none") return "";
  const days = `on ${r.days_with_2h_als} of ${r.full_days} days`;
  return r.als_median_delay_s == null ? days : `${days}, usually ${formatDelay(r.als_median_delay_s)}`;
}

/** "Queues (3)", or "Queues, Price (3 each)" when categories tie; null when no category has a complaint. */
export function topComplaintText(top: StationThemes["top"]): string | null {
  if (!top || top.categories.length === 0) return null;
  const names = top.categories.map(categoryName).join(", ");
  return `${names} (${top.count}${top.categories.length > 1 ? " each" : ""})`;
}

/** One table row: the site plus whichever of the two endpoints' entries exist for it (undefined when that endpoint is missing or failed). */
export interface StationRow {
  site: Site;
  /** Position in the server's queue-risk order; undefined when there is no entry. */
  riskIndex: number | undefined;
  risk: QueueRiskSite | undefined;
  themes: StationThemes | undefined;
}

export function buildRows(sites: Site[], risk: QueueRiskSite[] | null, themes: StationThemes[] | null): StationRow[] {
  const riskById = new Map((risk ?? []).map((r, i) => [r.site_id, { r, i }]));
  const themesById = new Map((themes ?? []).map((t) => [t.site_id, t]));
  return sites.map((site) => {
    const hit = riskById.get(site.site_id);
    return { site, riskIndex: hit?.i, risk: hit?.r, themes: themesById.get(site.site_id) };
  });
}

export type StationSort = "name" | "risk" | "complaints" | "top";

export const STATION_SORTS: { value: StationSort; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "risk", label: "Slower before than after" },
  { value: "complaints", label: "Queue complaints" },
  { value: "top", label: "Top complaint count" },
];

const byName = (a: StationRow, b: StationRow) => a.site.name.localeCompare(b.site.name);

/** Descending by a count; a station without data sorts after every station with one (even a 0). */
const byCountDesc = (value: (r: StationRow) => number | undefined) => (a: StationRow, b: StationRow) =>
  (value(b) ?? -1) - (value(a) ?? -1) || byName(a, b);

/** Name; queue risk in server order with "cannot tell" last (stations without a risk entry after those); or a complaint count, most first. Ties by name. */
export function sortRows(rows: StationRow[], sort: StationSort): StationRow[] {
  const sorted = [...rows];
  switch (sort) {
    case "name":
      return sorted.sort(byName);
    case "risk": {
      const rank = (r: StationRow) => (r.risk === undefined ? 2 : r.risk.tier === "cannot_tell" ? 1 : 0);
      return sorted.sort((a, b) => rank(a) - rank(b) || (a.riskIndex ?? 0) - (b.riskIndex ?? 0) || byName(a, b));
    }
    case "complaints":
      return sorted.sort(byCountDesc((r) => r.themes?.queue_complaints));
    case "top":
      return sorted.sort(byCountDesc((r) => (r.themes ? (r.themes.top?.count ?? 0) : undefined)));
  }
}
