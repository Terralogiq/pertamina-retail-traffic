import * as echarts from "echarts/core";
import { CHART_INK } from "./palette";

/** Name every chart host passes to echarts.init. Registered once, on import. */
export const CHART_THEME = "dashboard";

const axis = {
  axisLine: { lineStyle: { color: CHART_INK.axis } },
  axisTick: { lineStyle: { color: CHART_INK.axis } },
  axisLabel: { color: CHART_INK.muted, fontSize: 12 },
  splitLine: { lineStyle: { color: CHART_INK.grid } },
  nameTextStyle: { color: CHART_INK.muted, fontSize: 12 },
};

echarts.registerTheme(CHART_THEME, {
  backgroundColor: "transparent",
  textStyle: { fontFamily: getComputedFontFamily(), color: CHART_INK.text },
  title: { textStyle: { color: CHART_INK.text, fontSize: 14, fontWeight: 600 } },
  legend: { textStyle: { color: CHART_INK.text, fontSize: 12 }, itemWidth: 14, itemHeight: 8 },
  tooltip: {
    backgroundColor: CHART_INK.surface,
    borderColor: CHART_INK.axis,
    textStyle: { color: CHART_INK.text, fontSize: 12 },
  },
  categoryAxis: axis,
  valueAxis: axis,
  timeAxis: axis,
  line: { symbolSize: 6, lineStyle: { width: 2 } },
  bar: { itemStyle: { borderRadius: [2, 2, 0, 0] } },
});

function getComputedFontFamily(): string {
  if (typeof document === "undefined") return "system-ui, sans-serif";
  return getComputedStyle(document.documentElement).getPropertyValue("--font-sans").trim() || "system-ui, sans-serif";
}
