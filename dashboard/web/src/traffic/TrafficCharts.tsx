import { useEffect, useMemo, useState } from "react";
import { PatternCell, TrafficPoint, getSiteTimezones, getTrafficPattern, getTrafficSeries } from "./api";
import Chart from "./Chart";
import {
  DAYS,
  METRICS,
  MetricField,
  Range,
  baselineBuilding,
  BASELINE_FULL,
  heatmapData,
  legSeries,
  patternLegs,
  tzLabel,
  utcOffsetMinutes,
  windowStart,
} from "./model";

function lineOption(points: TrafficPoint[], field: MetricField, unit: string, offsetMin: number, tz: string) {
  return {
    useUTC: true, // timestamps are pre-shifted to site-local time (see legSeries)
    animation: false,
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 56, right: 16, top: 32, bottom: 28 },
    xAxis: { type: "time", name: tz, nameLocation: "end" },
    yAxis: { type: "value", scale: true, name: unit },
    series: legSeries(points, field, offsetMin).map(({ leg, data }) => ({
      name: leg, type: "line", showSymbol: false, connectNulls: false, data,
    })),
  };
}

function heatmapOption(cells: PatternCell[], leg: string) {
  const data = heatmapData(cells, leg);
  const values = data.map((d) => d[2]);
  return {
    animation: false,
    tooltip: {
      formatter: (p: { value: [number, number, number] }) =>
        `${DAYS[p.value[1]]} ${String(p.value[0]).padStart(2, "0")}:00 · ${p.value[2].toFixed(2)}`,
    },
    grid: { left: 48, right: 16, top: 8, bottom: 56 },
    xAxis: { type: "category", data: Array.from({ length: 24 }, (_, h) => h), splitArea: { show: true } },
    yAxis: { type: "category", data: DAYS, inverse: true, splitArea: { show: true } },
    visualMap: {
      min: values.length ? Math.min(...values) : 1,
      max: values.length ? Math.max(...values) : 2,
      calculable: true, orient: "horizontal", left: "center", bottom: 0,
      inRange: { color: ["#ffffcc", "#fd8d3c", "#800026"] },
    },
    series: [{ type: "heatmap", data }],
  };
}

export default function TrafficCharts({ siteId }: { siteId?: string }) {
  const [range, setRange] = useState<Range>("24h");
  const [timezone, setTimezone] = useState<string | null>(null);
  const [points, setPoints] = useState<TrafficPoint[] | null>(null);
  const [pattern, setPattern] = useState<PatternCell[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!siteId) return;
    let live = true;
    setTimezone(null);
    setPattern(null);
    setError("");
    getSiteTimezones()
      .then((sites) => live && setTimezone(sites.find((s) => s.site_id === siteId)?.timezone ?? null))
      .catch((e) => live && setError(String(e)));
    getTrafficPattern(siteId)
      .then((cells) => live && setPattern(cells))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [siteId]);

  useEffect(() => {
    if (!siteId) return;
    let live = true;
    setPoints(null);
    getTrafficSeries(siteId, windowStart(range, new Date()))
      .then((rows) => live && setPoints(rows))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [siteId, range]);

  const tz = tzLabel(timezone);
  const offsetMin = utcOffsetMinutes(timezone, new Date());
  const building = useMemo(() => (points ? baselineBuilding(points) : null), [points]);
  const lines = useMemo(
    () => (points ?? []).length === 0 ? [] : METRICS.map((m) => ({ ...m, option: lineOption(points!, m.field, m.unit, offsetMin, tz) })),
    [points, offsetMin, tz],
  );
  const legs = useMemo(() => patternLegs(pattern ?? []), [pattern]);

  if (!siteId) return null;
  return (
    <section>
      <h2>Traffic</h2>
      {error && <div role="alert">{error}</div>}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {(["24h", "7d"] as Range[]).map((r) => (
          <button key={r} onClick={() => setRange(r)} disabled={r === range}>
            {r === "24h" ? "24 h" : "7 d"}
          </button>
        ))}
        {building !== null && <span>baseline building ({building}/{BASELINE_FULL})</span>}
      </div>
      {points === null && <p>Loading…</p>}
      {points !== null && points.length === 0 && <p>No traffic data in this window.</p>}
      {lines.map((m) => (
        <div key={m.field}>
          <h3>{m.title}{m.unit && ` (${m.unit})`}</h3>
          <Chart option={m.option} height={220} />
        </div>
      ))}
      <h3>Mean congestion index by day and hour, last 28 days ({tz})</h3>
      {pattern !== null && legs.length === 0 && <p>No traffic data in this window.</p>}
      {pattern !== null &&
        legs.map((leg) => (
          <div key={leg}>
            <h4>{leg}</h4>
            <Chart option={heatmapOption(pattern, leg)} height={260} />
          </div>
        ))}
    </section>
  );
}
