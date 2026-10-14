import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { TrafficPoint, TypicalHour, TypicalLeg } from "./api";
import { TrafficTable, TypicalDayTable, ViewToggle } from "./ChartTable";

describe("ChartTable", () => {
  it("toggles between chart and table", () => {
    const html = renderToStaticMarkup(<ViewToggle mode="table" onChange={() => undefined} />);
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("Chart");
    expect(html).toContain("Table");
  });

  it("renders one traffic table row per point", () => {
    const points: TrafficPoint[] = [
      {
        selected_route_id: "r-approach",
        site_id: "s",
        leg: "approach",
        slot_time: "2026-10-07T12:00:00Z",
        duration_s: 100,
        delay_s: 20,
        congestion_index: 1.5,
        speed_kmh: 28,
        baseline_samples: 302,
      },
    ];
    const html = renderToStaticMarkup(<TrafficTable points={points} timezone="Asia/Jakarta" roadType="arterial" />);
    expect(html).toContain("Approach");
    expect(html).toContain("+20 s");
    expect(html).toContain("moderate");
    expect(html).toContain("28 km/h");
  });

  it("renders one typical-day table row per hour", () => {
    const hours: TypicalHour[] = [
      { hour: 8, median_delay_s: 40, p25_delay_s: 30, p75_delay_s: 50, n: 6, faded: false, busy: true },
      { hour: 9, median_delay_s: null, p25_delay_s: null, p75_delay_s: null, n: 0, faded: true, busy: false },
    ];
    const leg: TypicalLeg = { leg: "approach", day_kind: "weekday", hours, windows: [] };
    const html = renderToStaticMarkup(<TypicalDayTable legs={[leg]} timezone="Asia/Jakarta" />);
    expect(html).toContain("08:00");
    expect(html).toContain("Approach");
    expect(html).toContain("+40 s");
    expect(html).toContain("Yes");
    expect(html).not.toContain("09:00");
  });
});
