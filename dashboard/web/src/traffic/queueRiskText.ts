// Pure wording behind the "Queue risk (approach)" card. Neutral by design: the road is slower before the
// station than after it. Nothing built from the data says "queue" (docs/plans/queue-risk.md, "Screen proposal").
import type { DayKind, QueueRiskSiteDetail } from "./api";
import { formatDelay } from "./model";

/** Shown instead of the strip when the road past the station is slow as often as the road before it (tier cannot_tell). */
export const MASKED_TEXT =
  "Both sides of the station are slow together at these hours (area-wide congestion), so a station queue cannot be seen here.";

/** Under this share of a day kind's readings, with no approach-only busy hour, the headline says "rarely". */
const RARE_PCT = 5;

/** "07:00"; the exclusive end of a window that runs to midnight is "24:00". */
export const clock = (hour: number): string => `${String(hour === 24 ? 24 : hour % 24).padStart(2, "0")}:00`;
const dayWord = (dayKind: DayKind): string => (dayKind === "weekend" ? "weekends" : "weekdays");
const capitalise = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

export const isMasked = (entry: QueueRiskSiteDetail): boolean => entry.tier === "cannot_tell";

/** The fixed caption. The toll site's legs are about 1 km; every other site's are 500 m (from road_class). */
export function approachCaption(roadClass: "urban" | "toll" | null | undefined): string {
  const stretch = roadClass === "toll" ? "about 1 km" : "on the 500 m";
  return `Road traffic ${stretch} before the station, not a forecourt queue count.`;
}

/** "6.5 h"; a site with no slow-before-the-station slot has no run. */
export const longestRunText = (hours: number): string => (hours > 0 ? `${Number.isInteger(hours) ? hours : hours.toFixed(1)} h` : "-");

/** One sentence for the selected day kind, built from that kind's hours and approach-only busy windows. */
export function alsHeadline(entry: QueueRiskSiteDetail, dayKind: DayKind): string {
  if (!entry.ready) return "Not enough days yet.";
  const kind = entry.day_kinds.find((k) => k.day_kind === dayKind);
  const readings = kind?.hours.reduce((sum, h) => sum + h.n, 0) ?? 0;
  if (!kind || readings === 0) return `No ${dayKind} readings in the last 28 days.`;
  if (kind.hours.every((h) => h.n === 0 || h.faded)) {
    return `Not enough ${dayKind} readings yet: every hour has fewer than 4.`;
  }
  const label = capitalise(dayWord(dayKind));
  if (kind.windows.length > 0) {
    const spans = kind.windows.map((w) => `${clock(w.start_hour)}–${clock(w.end_hour)}`).join(", ");
    const delays = kind.hours.flatMap((h) => (h.approach_only_busy && h.approach_median_delay_s != null ? [h.approach_median_delay_s] : []));
    const low = formatDelay(Math.min(...delays));
    const high = formatDelay(Math.max(...delays));
    const usual = delays.length === 0 ? "" : `, usually ${low === high ? low : `${low} to ${high}`} over the usual time`;
    return `${label} ${spans}: slower before the station than after it${usual}.`;
  }
  const slow = kind.hours.reduce((sum, h) => sum + h.als_n, 0);
  const pct = Math.round((100 * slow) / readings);
  if (pct < RARE_PCT) return `${label}: rarely slower before the station than after it (${pct}% of readings).`;
  return `${label}: slower before the station than after it in ${pct}% of readings, with no single hour busy on that side alone.`;
}
