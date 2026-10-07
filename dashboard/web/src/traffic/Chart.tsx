import { CSSProperties, useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, HeatmapChart, LineChart, ScatterChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { CHART_THEME } from "../theme/echarts";
import "./Chart.css";

echarts.use([
  LineChart,
  BarChart,
  HeatmapChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

/**
 * The one ECharts host: one instance per mount, option replaced on change, resized with its container (not just
 * the window, so grid columns reflow it). Charts sharing a `group` move their axis pointers and tooltips together.
 */
export default function Chart({
  option,
  height,
  group,
  label,
}: {
  option: echarts.EChartsCoreOption;
  height: number;
  group?: string;
  label?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const instance = echarts.init(el.current!, CHART_THEME);
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(el.current!);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = chart.current;
    if (!instance || !group) return;
    instance.group = group;
    echarts.connect(group);
  }, [group]);

  useEffect(() => {
    chart.current?.setOption(option, true);
  }, [option]);

  return (
    <div
      ref={el}
      className="chart"
      role={label ? "img" : undefined}
      aria-label={label}
      style={{ "--chart-height": `${height}px` } as CSSProperties}
    />
  );
}
