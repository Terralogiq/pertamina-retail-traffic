import type { BusyWindow, DayKind, TypicalDayResponse, TypicalLeg } from "./api";
import { legLabel } from "./model";

function clock(hour: number): string {
  if (hour === 24) return "24:00";
  return `${String(((hour % 24) + 24) % 24).padStart(2, "0")}:00`;
}

/** "about 3 min slower than usual". Under a minute stays in seconds. Zero or less is no delay. */
export function delayPhrase(delayS: number | null): string {
  if (delayS == null) return "delay unknown";
  if (delayS <= 0) return "no delay";
  if (delayS < 60) return `about ${Math.round(delayS)} s slower than usual`;
  const minutes = Math.round(delayS / 6) / 10;
  const text = Number.isInteger(minutes) ? String(minutes) : minutes.toFixed(1);
  return `about ${text} min slower than usual`;
}

function busiest(legs: TypicalLeg[]): { leg: string; window: BusyWindow } | null {
  const rows = legs.flatMap((leg) => leg.windows.map((window) => ({ leg: leg.leg, window })));
  if (rows.length === 0) return null;
  return rows.reduce((best, row) => {
    const delay = row.window.median_delay_s ?? Number.NEGATIVE_INFINITY;
    const bestDelay = best.window.median_delay_s ?? Number.NEGATIVE_INFINITY;
    if (delay !== bestDelay) return delay > bestDelay ? row : best;
    if (row.window.start_hour !== best.window.start_hour) return row.window.start_hour < best.window.start_hour ? row : best;
    return row.leg.localeCompare(best.leg) < 0 ? row : best;
  });
}

/**
 * One sentence for a traffic card.
 * Ready: the busiest peak window. Otherwise a neutral line, even if windows were passed in.
 * `labelDay` prefixes the window sentence with Weekdays or Weekends, for a card that has no day-kind control.
 */
export function actionHeadline(ready: boolean, legs: TypicalLeg[], dayKind: DayKind, labelDay = false): string {
  if (!ready) return "Not enough days yet.";
  if (legs.length === 0) return "No readings for this day kind.";
  const peak = busiest(legs);
  if (!peak) return `No busy hours on ${dayKind === "weekend" ? "weekends" : "weekdays"}.`;
  const { leg, window } = peak;
  const sentence = `${legLabel(leg)} is slowest ${clock(window.start_hour)}–${clock(window.end_hour)}, ${delayPhrase(window.median_delay_s)}.`;
  const days = dayKind === "weekend" ? "Weekends" : "Weekdays";
  return labelDay ? `${days}: ${sentence}` : sentence;
}

/** Weekday headline for the recent-traffic card. Null until the profile has loaded. */
export function trafficHeadline(profile: TypicalDayResponse | null): string | null {
  if (!profile) return null;
  return actionHeadline(
    profile.ready,
    profile.legs.filter((leg) => leg.day_kind === "weekday"),
    "weekday",
    true,
  );
}
