import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AlsHour, DayKind, QueueRiskSiteDetail } from "./api";
import { AlsStrip, AlsTable, QueueRiskBody } from "./QueueRisk";
import { MASKED_TEXT, alsHeadline, approachCaption, longestRunText } from "./queueRiskText";

function hour(h: number, over: Partial<AlsHour> = {}): AlsHour {
  return { hour: h, n: 0, als_n: 0, als_pct: null, faded: true, approach_median_delay_s: null, approach_only_busy: false, ...over };
}

/** A full-reading hour: n readings, `als_n` of them slower before the station. */
function busy(h: number, als_n: number, delay: number, n = 10): AlsHour {
  return hour(h, { n, als_n, als_pct: (100 * als_n) / n, faded: n < 4, approach_median_delay_s: delay, approach_only_busy: true });
}

function kind(day_kind: DayKind, over: Record<number, AlsHour> = {}, windows: { s: number; e: number; m: number }[] = []) {
  const hours = Array.from({ length: 24 }, (_, h) => over[h] ?? hour(h));
  return {
    day_kind,
    hours,
    windows: windows.map((w) => ({ start_hour: w.s, end_hour: w.e, median_delay_s: w.m })),
  };
}

function entry(over: Partial<QueueRiskSiteDetail> = {}): QueueRiskSiteDetail {
  return {
    site_id: "61.761.03",
    tier: "moderate",
    als_pct: 31.1,
    both_slow_pct: 12.1,
    departure_only_pct: 0.6,
    days_with_2h_als: 14,
    full_days: 14,
    als_median_delay_s: 30,
    days: 14,
    ready: true,
    longest_run_h: 6.5,
    confidence: { level: "low", reason: "Every day for two weeks and late in the evening", as_of: "2026-10-21" },
    day_kinds: [
      kind("weekday", { 19: busy(19, 6, 30), 20: busy(20, 7, 33), 21: busy(21, 6, 36), 5: hour(5, { n: 10, als_n: 0, als_pct: 0, faded: false }) }, [{ s: 19, e: 22, m: 33 }]),
      kind("weekend", { 17: busy(17, 5, 62, 8), 18: busy(18, 5, 68, 8) }, [{ s: 17, e: 19, m: 65 }]),
    ],
    ...over,
  };
}

const masked = entry({ tier: "cannot_tell", als_pct: 0, confidence: { level: "none", reason: "Both sides are often slow together", as_of: "2026-10-21" } });

describe("queue-risk headline", () => {
  it("names the approach-only busy hours and the usual delay range for the selected day kind", () => {
    expect(alsHeadline(entry(), "weekday")).toBe(
      "Weekdays 19:00–22:00: slower before the station than after it, usually +30 s to +36 s over the usual time.",
    );
  });

  it("uses weekend data for the weekend control", () => {
    expect(alsHeadline(entry(), "weekend")).toBe(
      "Weekends 17:00–19:00: slower before the station than after it, usually +1.0 min to +1.1 min over the usual time.",
    );
  });

  it("lists several windows and runs to midnight as 24:00", () => {
    const e = entry({ day_kinds: [kind("weekday", { 7: busy(7, 6, 90), 22: busy(22, 6, 90), 23: busy(23, 6, 90) }, [{ s: 7, e: 8, m: 90 }, { s: 22, e: 24, m: 90 }]), kind("weekend")] });
    expect(alsHeadline(e, "weekday")).toBe(
      "Weekdays 07:00–08:00, 22:00–24:00: slower before the station than after it, usually +1.5 min over the usual time.",
    );
  });

  it("without a busy hour on the approach alone, states the share instead", () => {
    const quiet = (als_n: number) =>
      entry({ day_kinds: [kind("weekday", { 8: hour(8, { n: 10, als_n, als_pct: als_n * 10, faded: false }), 9: hour(9, { n: 10, als_n: 0, als_pct: 0, faded: false }) }), kind("weekend")] });
    expect(alsHeadline(quiet(0), "weekday")).toBe("Weekdays: rarely slower before the station than after it (0% of readings).");
    expect(alsHeadline(quiet(4), "weekday")).toBe(
      "Weekdays: slower before the station than after it in 20% of readings, with no single hour busy on that side alone.",
    );
  });

  it("says so when a day kind has no readings or only thin hours", () => {
    expect(alsHeadline(entry({ day_kinds: [kind("weekday")] }), "weekend")).toBe("No weekend readings in the last 28 days.");
    const thin = entry({ day_kinds: [kind("weekday"), kind("weekend", { 9: hour(9, { n: 3, als_n: 1, als_pct: 33, faded: true }) })] });
    expect(alsHeadline(thin, "weekend")).toBe("Not enough weekend readings yet: every hour has fewer than 4.");
  });

  it("says not enough days yet until the site has 7 local dates, for either day kind", () => {
    const early = entry({ days: 6, ready: false });
    expect(alsHeadline(early, "weekday")).toBe("Not enough days yet.");
    expect(alsHeadline(early, "weekend")).toBe("Not enough days yet.");
  });

  it("never says queue, for any site, day kind or branch", () => {
    const variants = [entry(), entry({ day_kinds: [kind("weekday", { 8: hour(8, { n: 10, als_n: 0, als_pct: 0, faded: false }) }), kind("weekend")] }), entry({ day_kinds: [] })];
    for (const e of variants) for (const d of ["weekday", "weekend"] as const) expect(alsHeadline(e, d).toLowerCase()).not.toContain("queue");
    expect(longestRunText(6.5).toLowerCase()).not.toContain("queue");
  });
});

describe("queue-risk wording", () => {
  it("fixes the caption and switches to about 1 km for the toll site", () => {
    expect(approachCaption("urban")).toBe("Road traffic on the 500 m before the station, not a forecourt queue count.");
    expect(approachCaption("toll")).toBe("Road traffic about 1 km before the station, not a forecourt queue count.");
  });

  it("writes the longest run in hours, or a dash when there is none", () => {
    expect(longestRunText(6.5)).toBe("6.5 h");
    expect(longestRunText(11)).toBe("11 h");
    expect(longestRunText(0)).toBe("-");
  });
});

describe("queue-risk card", () => {
  const render = (e: QueueRiskSiteDetail, dayKind: DayKind = "weekday", view: "chart" | "table" = "chart") =>
    renderToStaticMarkup(<QueueRiskBody entry={e} dayKind={dayKind} view={view} onViewChange={() => {}} />);

  it("masks a cannot_tell site: the fixed sentence, no strip, no facts, no confidence chip", () => {
    const html = render(masked);
    expect(html).toContain(MASKED_TEXT);
    expect(html).not.toContain("als-strip");
    expect(html).not.toContain("queue-facts");
    expect(html).not.toContain("confidence-chip");
    expect(html).not.toContain('aria-label="View"'); // the table toggle
    expect(html).toContain("not a forecourt queue count");
    expect(html).toContain('href="#review-themes"');
  });

  it("shows headline, strip, three facts, confidence with its reason, caption and the reviews pointer", () => {
    const html = render(entry());
    expect(html).toContain("Weekdays 19:00–22:00");
    expect(html).toContain("als-strip");
    expect(html).toContain("14 of 14");
    expect(html).toContain("+30 s");
    expect(html).toContain("6.5 h");
    expect(html).toContain("Confidence: Low");
    expect(html).toContain("Every day for two weeks and late in the evening");
    expect(html).toContain("on the 500 m before the station");
    expect(html).toContain('aria-label="View"'); // Chart / Table toggle
    expect(html).toContain("sampled reviews, weak evidence");
    expect(html).toContain('href="#review-themes"');
    expect(html.indexOf("als-strip")).toBeLessThan(html.indexOf("queue-facts"));
    expect(html.indexOf("queue-facts")).toBeLessThan(html.indexOf("confidence-chip"));
    expect(html.indexOf("confidence-chip")).toBeLessThan(html.indexOf("not a forecourt queue count"));
  });

  it("outlines approach-only busy hours and fades hours under 4 readings", () => {
    const hours = entry().day_kinds[1].hours.map((h) => (h.hour === 17 ? { ...h, n: 3, faded: true } : h));
    const html = renderToStaticMarkup(<AlsStrip hours={hours} />);
    const cell = (h: number) => html.match(new RegExp(`<li[^>]*data-hour="${h}"[^>]*>`))?.[0] ?? "";
    expect(cell(17)).toContain('data-faded="true"');
    expect(cell(17)).toContain("is-faded");
    expect(cell(17)).toContain("is-outlined");
    expect(cell(18)).toContain('data-faded="false"');
    expect(cell(18)).not.toContain("is-faded");
    expect(cell(18)).toContain("is-outlined");
    expect(cell(18)).toContain("--share:0.625");
    expect(cell(3)).toContain('data-n="0"');
    expect(cell(3)).not.toContain("is-outlined");
    expect((html.match(/<li[^>]*data-hour=/g) ?? []).length).toBe(24);
  });

  it("offers the same hours as a table, leaving out hours with no reading", () => {
    const html = renderToStaticMarkup(<AlsTable hours={entry().day_kinds[0].hours} />);
    expect((html.match(/<tr/g) ?? []).length).toBe(1 + 4); // header, 05:00, 19:00, 20:00, 21:00
    expect(html).toContain("19:00");
    expect(html).not.toContain("03:00");
  });

  it("swaps the strip for the table in table view", () => {
    const html = render(entry(), "weekday", "table");
    expect(html).toContain("chart-table");
    expect(html).not.toContain("als-strip");
  });

  it("uses the toll caption from road_class", () => {
    const html = renderToStaticMarkup(
      <QueueRiskBody entry={entry()} site={{ road_class: "toll" } as never} dayKind="weekday" view="chart" onViewChange={() => {}} />,
    );
    expect(html).toContain("about 1 km before the station");
  });

  it("builds no queue claim from the data: only the prescribed caption and review topics say it", () => {
    const html = render(entry());
    const text = html.replace(/<[^>]+>/g, " ");
    const without = text
      .replace("not a forecourt queue count", "")
      .replace(/Queue risk \(approach\)/g, "")
      .replace(/“Queues”/g, "");
    expect(without.toLowerCase()).not.toContain("queue");
  });
});
