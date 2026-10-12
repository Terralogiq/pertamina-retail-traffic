import type { BusyWindow, DayKind, TypicalHour, TypicalLeg } from "./api";
import { formatDelay, legLabel } from "./model";
import "./TrafficCharts.css";

const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

function clock(hour: number): string {
  if (hour === 24) return "24:00";
  return `${String(((hour % 24) + 24) % 24).padStart(2, "0")}:00`;
}

/** Hours covered by a window. `end_hour` is exclusive; a smaller end wraps past midnight. */
function hoursIn(window: BusyWindow): number[] {
  if (window.end_hour === 24 || window.end_hour > window.start_hour) {
    const end = window.end_hour === 24 ? 24 : window.end_hour;
    return Array.from({ length: end - window.start_hour }, (_, i) => window.start_hour + i);
  }
  return [
    ...Array.from({ length: 24 - window.start_hour }, (_, i) => window.start_hour + i),
    ...Array.from({ length: window.end_hour }, (_, i) => i),
  ];
}

/** "Weekdays · Approach · 07:00–09:00 · usually +2.0 min to +4.0 min slower". */
export function busyWindowText(dayKind: DayKind, leg: string, window: BusyWindow, hours: TypicalHour[]): string {
  const byHour = new Map(hours.map((hour) => [hour.hour, hour.median_delay_s]));
  const medians = hoursIn(window)
    .map((hour) => byHour.get(hour))
    .filter((value): value is number => value != null);
  const low = Math.min(...medians);
  const high = Math.max(...medians);
  const usual = medians.length === 0 ? "n/a" : low === high ? formatDelay(low) : `${formatDelay(low)} to ${formatDelay(high)}`;
  const days = dayKind === "weekday" ? "Weekdays" : "Weekends";
  return `${days} · ${legLabel(leg)} · ${clock(window.start_hour)}–${clock(window.end_hour)} · usually ${usual} slower`;
}

/** 24 cells. A filled cell is a busy hour. */
export function BusyStrip({ leg, hours }: { leg: string; hours: TypicalHour[] }) {
  const byHour = new Map(hours.map((hour) => [hour.hour, hour.busy]));
  return (
    <ol className="busy-strip" aria-label={`${legLabel(leg)} busy hours`}>
      {HOURS.map((hour) => {
        const busy = byHour.get(hour) ?? false;
        return (
          <li key={hour} data-hour={hour} data-busy={busy ? "true" : "false"} className={busy ? "busy-cell is-busy" : "busy-cell"} />
        );
      })}
    </ol>
  );
}

/** Peak-window list and 24-cell strip for one day kind. The caller hides this until the profile is ready. */
export default function BusyHours({ legs, dayKind }: { legs: TypicalLeg[]; dayKind: DayKind }) {
  const lines = legs.flatMap((leg) => leg.windows.map((window) => ({ leg: leg.leg, window, hours: leg.hours })));
  const kind = dayKind === "weekday" ? "weekdays" : "weekends";
  return (
    <div className="busy-hours">
      {lines.length === 0 ? (
        <p className="typical-caption">No busy hours on {kind}.</p>
      ) : (
        <ul className="busy-list">
          {lines.map(({ leg, window, hours }) => (
            <li key={`${leg}-${window.start_hour}`}>{busyWindowText(dayKind, leg, window, hours)}</li>
          ))}
        </ul>
      )}
      {legs.map((leg) => (
        <BusyStrip key={leg.leg} leg={leg.leg} hours={leg.hours} />
      ))}
    </div>
  );
}
