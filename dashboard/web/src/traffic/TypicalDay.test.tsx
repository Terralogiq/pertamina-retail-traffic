import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { TypicalDayResponse, TypicalHour, TypicalLeg } from "./api";
import TypicalDay, { HourStrip, TypicalDayBody, typicalChartOption, typicalNote } from "./TypicalDay";

function hour(hour: number, n: number, median: number | null): TypicalHour {
  return {
    hour,
    median_delay_s: median,
    p25_delay_s: median == null ? null : median - 10,
    p75_delay_s: median == null ? null : median + 10,
    n,
    faded: n < 4,
    busy: false,
  };
}

function leg(name: string, kind: "weekday" | "weekend"): TypicalLeg {
  const hours = Array.from({ length: 24 }, (_, h) => hour(h, 0, null));
  hours[8] = hour(8, 2, 40);
  hours[9] = hour(9, 6, 80);
  return { leg: name, day_kind: kind, hours, windows: [] };
}

const data: TypicalDayResponse = {
  days: 6,
  ready: false,
  legs: [leg("approach", "weekday"), leg("departure", "weekday"), leg("approach", "weekend"), leg("departure", "weekend")],
};

describe("typical day", () => {
  it("states how many days the profile rests on", () => {
    expect(typicalNote(6, false)).toBe("Based on 6 days. Needs 1 more day.");
    expect(typicalNote(1, false)).toBe("Based on 1 day. Needs 6 more days.");
    expect(typicalNote(7, true)).toBe("Based on 7 days.");
    expect(typicalNote(0, false)).toBe("Based on 0 days. Needs 7 more days.");
  });

  it("fades an hour with fewer than 4 readings and keeps a full hour solid", () => {
    const html = renderToStaticMarkup(<HourStrip leg="approach" hours={leg("approach", "weekday").hours} />);
    const tick = (hour: number) => html.match(new RegExp(`<li[^>]*data-hour="${hour}"[^>]*>`))?.[0] ?? "";
    expect(tick(8)).toContain('data-n="2"');
    expect(tick(8)).toContain('data-faded="true"');
    expect(tick(8)).toContain("is-faded");
    expect(tick(9)).toContain('data-n="6"');
    expect(tick(9)).toContain('data-faded="false"');
    expect(tick(9)).not.toContain("is-faded");
  });

  it("draws the thin hour on the faded median series and the full hour on the solid one", () => {
    const opt = typicalChartOption([leg("approach", "weekday")]);
    const solid = opt.series.find((series) => series.id === "median-approach");
    const faded = opt.series.find((series) => series.id === "median-faded-approach");
    expect(solid?.data[8]).toBeNull();
    expect(faded?.data[8]).toBe(40);
    expect(solid?.data[9]).toBe(80);
    expect(faded?.data[9]).toBeNull();
    expect(faded?.lineStyle).toMatchObject({ opacity: 0.35 });
    const band = opt.series.find((series) => series.id === "band-approach");
    expect(band?.data[9]).toBe(20);
    expect(band?.stack).toBe("band-approach");
  });

  it("shows the readiness note and both day kinds", () => {
    const html = renderToStaticMarkup(<TypicalDayBody data={data} dayKind="weekday" />);
    expect(html).toContain("Based on 6 days. Needs 1 more day.");
    expect(html).toContain("Approach");
    expect(html).toContain("Departure");
    const section = renderToStaticMarkup(<TypicalDay siteId="74.902.22" timezone="Asia/Jakarta" />);
    expect(section).toContain("Typical day");
    expect(section).toContain("Weekday");
    expect(section).toContain("Weekend");
    expect(section).toContain('aria-pressed="true"');
  });
});
