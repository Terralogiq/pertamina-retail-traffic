import { describe, expect, it } from "vitest";
import type { PatternCell } from "./api";
import { heatmapOption } from "./TrafficCharts";

describe("heatmapOption", () => {
  it("puts every heatmap series under a visualMap (ECharts throws otherwise)", () => {
    const cells = [{ dow: 3, hour: 8, leg: "approach", mean_congestion: 1.4, mean_speed_kmh: 30, n: 2 }] as PatternCell[];
    const opt = heatmapOption(cells, "approach");
    const covered = new Set(opt.visualMap.map((v) => v.seriesIndex));
    opt.series.forEach((s, i) => {
      if (s.type === "heatmap") expect(covered.has(i)).toBe(true);
    });
  });
});
