import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { TypicalHour, TypicalLeg } from "./api";
import BusyHours, { busyWindowText } from "./BusyHours";
import { TypicalDayBody } from "./TypicalDay";

function hours(busyAt: number[], medians: Record<number, number> = {}): TypicalHour[] {
  return Array.from({ length: 24 }, (_, hour) => ({
    hour,
    median_delay_s: medians[hour] ?? (busyAt.includes(hour) ? 40 : 0),
    p25_delay_s: null,
    p75_delay_s: null,
    n: 4,
    faded: false,
    busy: busyAt.includes(hour),
  }));
}

function leg(busyAt: number[], windows: TypicalLeg["windows"], medians?: Record<number, number>): TypicalLeg {
  return { leg: "approach", day_kind: "weekday", hours: hours(busyAt, medians), windows };
}

describe("busy hours", () => {
  it("names a peak window in minutes", () => {
    const row = leg([7, 8], [{ start_hour: 7, end_hour: 9, median_delay_s: 180 }], { 7: 120, 8: 240 });
    expect(busyWindowText("weekday", "approach", row.windows[0], row.hours)).toBe(
      "Weekdays · Approach · 07:00–09:00 · usually +2.0 min to +4.0 min slower",
    );
  });

  it("fills the busy cells and hides the strip until the profile is ready", () => {
    const ready = renderToStaticMarkup(
      <BusyHours legs={[leg([7, 8], [{ start_hour: 7, end_hour: 9, median_delay_s: 40 }])]} dayKind="weekday" />,
    );
    const cell = (hour: number) => ready.match(new RegExp(`<li[^>]*data-hour="${hour}"[^>]*>`))?.[0] ?? "";
    expect(cell(7)).toContain('data-busy="true"');
    expect(cell(7)).toContain("is-busy");
    expect(cell(7)).toContain('title="07:00"');
    expect(ready).toContain(">Approach<");
    expect(cell(6)).toContain('data-busy="false"');
    expect(cell(6)).not.toContain("is-busy");
    expect(ready).toContain("07:00–09:00");

    const waiting = renderToStaticMarkup(
      <TypicalDayBody
        data={{ days: 6, ready: false, legs: [leg([7], [])] }}
        dayKind="weekday"
      />,
    );
    expect(waiting).toContain("Needs 1 more day");
    expect(waiting).not.toContain("data-busy");
    expect(waiting).not.toContain("07:00");
  });
});
