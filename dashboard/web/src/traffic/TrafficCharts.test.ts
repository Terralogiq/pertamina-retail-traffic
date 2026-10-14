import { describe, expect, it } from "vitest";
import type { TrafficPoint } from "./api";
import { delayOption } from "./TrafficCharts";

function point(leg: string, extra: Partial<TrafficPoint> = {}): TrafficPoint {
  return {
    selected_route_id: `r-${leg}`,
    site_id: "s",
    leg,
    slot_time: "2026-10-07T01:00:00Z",
    duration_s: 100,
    delay_s: 20,
    congestion_index: 1.5,
    speed_kmh: 28,
    baseline_samples: 302,
    ...extra,
  };
}

describe("delayOption", () => {
  it("draws one delay line per leg and keeps speed and usual time in the tooltip", () => {
    const opt = delayOption(
      [point("approach"), point("departure", { delay_s: 75, speed_kmh: 12, congestion_index: 2.4 })],
      0,
      { min: 0, max: 1 },
    );
    expect(opt.series.map((series) => series.name)).toEqual(["Approach", "Departure"]);
    expect(opt.series.every((series) => series.type === "line")).toBe(true);
    const text = opt.tooltip.formatter([
      { seriesName: "Approach", value: [0, 20], data: { value: [0, 20], speed_kmh: 28, congestion_index: 1.5 } },
    ]);
    expect(text).toContain("28 km/h");
    expect(text).toContain("1.50× usual time");
    expect(text).not.toContain("km/h · km/h");
  });
});
