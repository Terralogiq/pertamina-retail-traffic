import type { EChartsCoreOption } from "echarts/core";
import Chart from "../traffic/Chart";

/** Weather and rain charts use the same host as the traffic charts (one registration, one resize behaviour). */
export function EChart({ option, height = 260 }: { option: EChartsCoreOption; height?: number }) {
  return <Chart option={option} height={height} />;
}
