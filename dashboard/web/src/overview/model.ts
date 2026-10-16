// Pure helpers behind the overview station list: the two signals, the potential-queue groups, row wording,
// list orders, the summary line and the selection state.
import type { Site } from "../map/api";
import type { SiteState } from "../map/severity";
import { categoryName } from "../reviews/model";
import type { ConfidenceLevel, QueueRiskSite, StationThemes } from "./api";

export const CONFIDENCE_LABELS: Record<ConfidenceLevel, string> = {
  medium: "Medium",
  low: "Low",
  very_low: "Very low",
  none: "None",
};

/** A signal for one station; "unknown" when its endpoint failed or has no entry for the station. */
export type SignalState = "yes" | "no" | "unknown";

export type QueueGroup = "potential" | "traffic_only" | "reviews_only" | "none";

/** List and legend order: both signals first, no signal last. */
export const GROUP_ORDER: QueueGroup[] = ["potential", "traffic_only", "reviews_only", "none"];

export const GROUP_LABELS: Record<QueueGroup, string> = {
  potential: "Potential queue",
  traffic_only: "Traffic only",
  reviews_only: "Reviews only",
  none: "No signal",
};

/** Marker text: short enough for a map pill (see MARKER_BOX_WIDE). */
export const GROUP_MARKER_TEXT: Record<QueueGroup, string> = {
  potential: "Potential",
  traffic_only: "Traffic",
  reviews_only: "Reviews",
  none: "No signal",
};

/** Traffic signal: slower before the station than after it on at least 70% of days. "Cannot tell" never counts. */
export function trafficSignal(risk: QueueRiskSite | undefined): SignalState {
  if (!risk) return "unknown";
  return risk.tier === "strong" || risk.tier === "moderate" ? "yes" : "no";
}

/** Review signal: at least one review from the last 12 months says the queue reaches the road. */
export function reviewSignal(themes: StationThemes | undefined): SignalState {
  if (!themes) return "unknown";
  return themes.road_queue_recent >= 1 ? "yes" : "no";
}

/** An unknown signal groups as absent; the row says it is unavailable, so it is never silently a "no". */
export function groupOf(traffic: SignalState, reviews: SignalState): QueueGroup {
  const t = traffic === "yes";
  const r = reviews === "yes";
  return t && r ? "potential" : t ? "traffic_only" : r ? "reviews_only" : "none";
}

/** One list row: the site plus whichever of the two endpoints' entries exist for it (undefined when that endpoint is missing or failed). */
export interface StationRow {
  site: Site;
  /** Position in the server's queue-risk order; undefined when there is no entry. */
  riskIndex: number | undefined;
  risk: QueueRiskSite | undefined;
  themes: StationThemes | undefined;
  traffic: SignalState;
  reviews: SignalState;
  group: QueueGroup;
  /** The road after the station is slower, so the traffic signal cannot be read here. */
  cannotTell: boolean;
}

export function buildRows(sites: Site[], risk: QueueRiskSite[] | null, themes: StationThemes[] | null): StationRow[] {
  const riskById = new Map((risk ?? []).map((r, i) => [r.site_id, { r, i }]));
  const themesById = new Map((themes ?? []).map((t) => [t.site_id, t]));
  return sites.map((site) => {
    const hit = riskById.get(site.site_id);
    const t = themesById.get(site.site_id);
    const traffic = trafficSignal(hit?.r);
    const reviews = reviewSignal(t);
    return {
      site,
      riskIndex: hit?.i,
      risk: hit?.r,
      themes: t,
      traffic,
      reviews,
      group: groupOf(traffic, reviews),
      cannotTell: hit?.r.tier === "cannot_tell",
    };
  });
}

/** Potential queues first, then traffic only, reviews only, no signal; within a group the server's queue-risk order (no entry last, then name). */
export function orderByGroup(rows: StationRow[]): StationRow[] {
  const rank = (r: StationRow) => GROUP_ORDER.indexOf(r.group);
  return [...rows].sort(
    (a, b) =>
      rank(a) - rank(b) ||
      (a.riskIndex ?? Infinity) - (b.riskIndex ?? Infinity) ||
      a.site.name.localeCompare(b.site.name),
  );
}

/** "Traffic now": the live ranking (worst first, see rankSites). */
export function orderByRank(rows: StationRow[], ranked: SiteState[]): StationRow[] {
  const byId = new Map(rows.map((r) => [r.site.site_id, r]));
  return ranked.flatMap((s) => byId.get(s.site.site_id) ?? []);
}

const COUNT_TEXT: Record<Exclude<QueueGroup, "none">, (n: number) => string> = {
  potential: (n) => `${n} potential ${n === 1 ? "queue" : "queues"}`,
  traffic_only: (n) => `${n} traffic only`,
  reviews_only: (n) => `${n} reviews only`,
};

/** "1 potential queue · 3 traffic only · 3 reviews only"; groups with no station and "no signal" are left out. */
export function groupSummary(rows: StationRow[]): string {
  const parts = (Object.keys(COUNT_TEXT) as (keyof typeof COUNT_TEXT)[]).flatMap((g) => {
    const n = rows.filter((r) => r.group === g).length;
    return n > 0 ? [COUNT_TEXT[g](n)] : [];
  });
  return parts.length ? parts.join(" · ") : "No station shows a signal";
}

export const CANNOT_TELL_TEXT = "Traffic can't tell here: the road after the station is slower";

/** The traffic signal in words. Never says "queue": road data alone does not show one. */
export function trafficLine(risk: QueueRiskSite | undefined): string {
  if (!risk) return "Slowdown comparison unavailable";
  const { tier, days_with_2h_als: days, full_days: full } = risk;
  switch (tier) {
    case "cannot_tell":
      return CANNOT_TELL_TEXT;
    case "strong":
    case "moderate":
      return `Slower before than after on ${days} of ${full} days`;
    case "weak":
      return `Slower before than after on only ${days} of ${full} days`;
    case "none":
      return `Not slower before than after on any of ${full} days`;
  }
}

export function reviewLine(themes: StationThemes | undefined): string {
  if (!themes) return "Reviews unavailable";
  const n = themes.road_queue_recent;
  return n === 0 ? "No review says the queue reaches the road" : `${n} ${n === 1 ? "review" : "reviews"}: queue reaches the road`;
}

export const complaintsLine = (themes: StationThemes): string => `Queue complaints: ${themes.queue_recent} in the last 12 months`;

/** "Queues (3)", or "Queues, Price (3 each)" when categories tie; null when no category has a complaint. */
export function topComplaintText(top: StationThemes["top"]): string | null {
  if (!top || top.categories.length === 0) return null;
  const names = top.categories.map(categoryName).join(", ");
  return `${names} (${top.count}${top.categories.length > 1 ? " each" : ""})`;
}

/** What the map colours and the list order follow: the potential-queue groups, or live traffic. */
export type MapMode = "potential" | "now";

/** Without the traffic comparison there are no groups to show, so a failed queue-risk load falls back to "Traffic now". */
export const effectiveMode = (chosen: MapMode, risk: unknown): MapMode => (risk instanceof Error ? "now" : chosen);

/** The selected station's id, shared by the map and the list; null when none. */
export type Selection = string | null;

export type SelectionAction =
  /** A row: selects it, or clears when it is already selected. */
  | { type: "toggle"; siteId: string }
  /** A marker: selects it. */
  | { type: "select"; siteId: string }
  /** Escape. */
  | { type: "clear" };

export function selectionReducer(state: Selection, action: SelectionAction): Selection {
  switch (action.type) {
    case "toggle":
      return state === action.siteId ? null : action.siteId;
    case "select":
      return action.siteId;
    case "clear":
      return null;
  }
}
