import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { TypicalDayResponse, TypicalHour, TypicalLeg } from "./api";
import TypicalDay, { HourStrip, TypicalDayBody, delayStep, maxMedian, typicalChartOption, typicalNote } from "./TypicalDay";

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
    const html = renderToStaticMarkup(<HourStrip leg="approach" hours={leg("approach", "weekday").hours} max={80} />);
    const tick = (hour: number) => html.match(new RegExp(`<li[^>]*data-hour="${hour}"[^>]*>`))?.[0] ?? "";
    expect(tick(8)).toContain('data-n="2"');
    expect(tick(8)).toContain('data-faded="true"');
    expect(tick(8)).toContain("is-faded");
    expect(tick(9)).toContain('data-n="6"');
    expect(tick(9)).toContain('data-faded="false"');
    expect(tick(9)).not.toContain("is-faded");
  });

  it("draws 24 cells per leg, each with its hour and median delay as text and a label with the reading count", () => {
    const html = renderToStaticMarkup(<HourStrip leg="approach" hours={leg("approach", "weekday").hours} max={80} />);
    expect(html.match(/<li\b/g)?.length).toBe(24);
    expect(html).toContain('aria-label="Approach median delay by hour"');
    expect(html).toContain('<span class="hour-tick-label">08</span><span class="hour-tick-value num">+40 s</span>');
    expect(html).toContain('<span class="hour-tick-label">09</span><span class="hour-tick-value num">+1.3 min</span>');
    expect(html).toContain('aria-label="Approach, hour 08: median +40 s, 2 readings, thin sample"');
    expect(html).toContain('aria-label="Approach, hour 09: median +1.3 min, 6 readings"');
    expect(html).toContain('aria-label="Approach, hour 00: no data, 0 readings, thin sample"');
    expect(html.match(/hour-tick-value num">-</g)?.length).toBe(22);
  });

  it("colours by one scale across both legs: the slowest hour is step 5, an empty hour has no step", () => {
    expect(delayStep(80, 80)).toBe(5);
    expect(delayStep(40, 80)).toBe(3);
    expect(delayStep(1, 80)).toBe(1);
    expect(delayStep(0, 80)).toBe(1);
    expect(maxMedian([leg("approach", "weekday"), leg("departure", "weekday")])).toBe(80);
    const html = renderToStaticMarkup(<HourStrip leg="departure" hours={leg("departure", "weekday").hours} max={160} />);
    expect(html.match(/<li[^>]*data-hour="9"[^>]*>/)?.[0]).toContain('data-step="3"');
    expect(html.match(/<li[^>]*data-hour="0"[^>]*>/)?.[0]).not.toContain("data-step");
  });

  it("explains the strips: median delay caption, the faded rule and the ramp", () => {
    const html = renderToStaticMarkup(<TypicalDayBody data={data} dayKind="weekday" view="chart" onViewChange={() => undefined} />);
    expect(html).toContain("Median delay by hour. Faded hours have fewer than 4 readings.");
    expect(html).not.toContain("Count under each hour");
    expect(html).toContain("no delay");
    expect(html).toContain("+1.3 min");
    expect(html.match(/class="hour-strip"/g)?.length).toBe(2);
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
    const html = renderToStaticMarkup(<TypicalDayBody data={data} dayKind="weekday" view="chart" onViewChange={() => undefined} />);
    expect(html).toContain("Based on 6 days. Needs 1 more day.");
    expect(html).toContain("Not enough days yet.");
    expect(html).not.toContain("is slowest");
    expect(html).toContain("Approach");
    expect(html).toContain("Departure");
    expect(html).toContain('aria-label="View"');
    expect(html).toContain("Chart");
    expect(html).toContain("Table");
    const section = renderToStaticMarkup(<TypicalDay siteId="74.902.22" timezone="Asia/Jakarta" />);
    expect(section).toContain("Typical day");
    expect(section).toContain("Weekday");
    expect(section).toContain("Weekend");
    expect(section).toContain('aria-pressed="true"');
  });

  it("renders the table with one row per hour when the view is table", () => {
    const html = renderToStaticMarkup(<TypicalDayBody data={data} dayKind="weekday" view="table" onViewChange={() => undefined} />);
    const rows = html.match(/<tbody[^>]*>([\s\S]*?)<\/tbody>/)?.[1] ?? "";
    expect(rows.match(/<tr\b/g)?.length).toBe(4);
    expect(html).toContain("08:00");
    expect(html).toContain("09:00");
    expect(html).toContain("Approach");
    expect(html).toContain("Departure");
    expect(html).toContain("+40 s");
    expect(html).toContain("+1.3 min");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-pressed="false"');
  });

  it("names the busiest window once the profile is ready", () => {
    const ready: TypicalDayResponse = {
      days: 7,
      ready: true,
      legs: [
        {
          ...leg("departure", "weekday"),
          windows: [{ start_hour: 17, end_hour: 18, median_delay_s: 60 }],
        },
        {
          ...leg("approach", "weekday"),
          windows: [{ start_hour: 7, end_hour: 9, median_delay_s: 180 }],
        },
      ],
    };
    const html = renderToStaticMarkup(<TypicalDayBody data={ready} dayKind="weekday" view="chart" onViewChange={() => undefined} />);
    expect(html).toContain("Approach is slowest 07:00–09:00, about 3 min slower than usual.");
  });
});
