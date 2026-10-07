import { useEffect, useMemo, useState } from "react";
import { Block, Notice, Section, Skeleton } from "../site/Section";
import { CHART_INK, SEQUENTIAL, SERIES } from "../theme/palette";
import { WeatherSeriesPoint, getWeatherSeries } from "../weather/api";
import { PatternCell, TrafficPoint, getTrafficPattern, getTrafficSeries } from "./api";
import Chart from "./Chart";
import {
  DAYS,
  HEATMAP_SCALE,
  METRICS,
  MetricField,
  Range,
  emptyCells,
  hadRain,
  heatmapData,
  legLabel,
  legSeries,
  patternLegs,
  precipitationSeries,
  tzLabel,
  utcOffsetMinutes,
  windowStart,
} from "./model";
import "./TrafficCharts.css";

const LINE_HEIGHT = 200;
const RAIN_HEIGHT = 96;
const HEATMAP_HEIGHT = 216;
// Same plot inset on every time chart, so the rain strip lines up under the traffic lines.
const GRID = { left: 52, right: 16, top: 12, bottom: 24 };
const RANGES: { id: Range; label: string }[] = [
  { id: "24h", label: "24 h" },
  { id: "7d", label: "7 days" },
];

const legColor = (leg: string) => SERIES[leg as "approach" | "departure"] ?? CHART_INK.text;

/** Midnight reads "7 Oct" instead of a bare day number; other ticks are clock times. */
const TIME_LABELS = { day: "{d} {MMM}", hour: "{HH}:{mm}", minute: "{HH}:{mm}" };

function lineOption(points: TrafficPoint[], field: MetricField, unit: string, offsetMin: number, x: { min: number; max: number }) {
  const lines = legSeries(points, field, offsetMin).map(({ leg, data }) => ({
    name: legLabel(leg),
    type: "line",
    showSymbol: false,
    connectNulls: false,
    data,
    color: legColor(leg),
    lineStyle: { width: 2 },
    // The congestion index reads against free flow: a quiet reference line at 1.0.
    markLine:
      field === "congestion_index"
        ? {
            silent: true,
            symbol: "none",
            lineStyle: { color: CHART_INK.axis, type: "dashed", width: 1 },
            label: { formatter: "free flow", color: CHART_INK.muted, fontSize: 12, position: "insideEndTop" },
            data: [{ yAxis: 1 }],
          }
        : undefined,
  }));
  return {
    useUTC: true, // timestamps are pre-shifted to site-local time (see legSeries)
    animation: false,
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number | null) => (v == null ? "n/a" : `${field === "congestion_index" ? v.toFixed(2) : Math.round(v)}${unit ? ` ${unit}` : ""}`),
    },
    grid: GRID,
    xAxis: { type: "time", min: x.min, max: x.max, axisLabel: { formatter: TIME_LABELS } },
    yAxis: { type: "value", scale: true, splitNumber: 3 },
    series: lines,
  };
}

function rainOption(rain: [number, number][], x: { min: number; max: number }) {
  return {
    useUTC: true,
    animation: false,
    tooltip: { trigger: "axis", valueFormatter: (v: number) => `${v.toFixed(1)} mm` },
    grid: GRID,
    xAxis: { type: "time", min: x.min, max: x.max, axisLabel: { formatter: TIME_LABELS } },
    yAxis: { type: "value", min: 0, splitNumber: 2 },
    series: [{ name: "Rain", type: "bar", data: rain, barMaxWidth: 6, itemStyle: { color: SERIES.rain } }],
  };
}

export function heatmapOption(cells: PatternCell[], leg: string) {
  const clamp = (v: number) => Math.min(HEATMAP_SCALE.max, Math.max(HEATMAP_SCALE.min, v));
  // [hour, day, colour value, real value]: colour clamps to the fixed scale, the tooltip keeps the real mean.
  const data = heatmapData(cells, leg).map(([h, d, v]) => [h, d, clamp(v), v]);
  const empty = emptyCells(cells, leg).map(([h, d]) => [h, d, 0]);
  const cell = { borderColor: CHART_INK.surface, borderWidth: 2 };
  const hh = (h: number) => String(h).padStart(2, "0");
  return {
    animation: false,
    tooltip: {
      formatter: (p: { seriesIndex: number; value: number[] }) =>
        `${DAYS[p.value[1]]} ${hh(p.value[0])}:00 · ${p.seriesIndex === 0 ? p.value[3].toFixed(2) : "no data"}`,
    },
    grid: { left: 40, right: 8, top: 4, bottom: 24 },
    xAxis: {
      type: "category",
      data: Array.from({ length: 24 }, (_, h) => hh(h)),
      axisLabel: { interval: 2 },
      axisTick: { show: false },
      splitArea: { show: false },
    },
    yAxis: { type: "category", data: DAYS, inverse: true, axisTick: { show: false }, splitArea: { show: false } },
    // ECharts requires every heatmap series to sit under a visualMap: the second one paints the "no data" cells flat.
    visualMap: [
      {
        show: false,
        seriesIndex: 0,
        dimension: 2,
        min: HEATMAP_SCALE.min,
        max: HEATMAP_SCALE.max,
        inRange: { color: [...SEQUENTIAL] },
      },
      { show: false, seriesIndex: 1, dimension: 2, min: 0, max: 1, inRange: { color: [CHART_INK.grid, CHART_INK.grid] } },
    ],
    series: [
      { type: "heatmap", data, itemStyle: cell, emphasis: { itemStyle: { borderColor: CHART_INK.text } } },
      { type: "heatmap", data: empty, itemStyle: cell, emphasis: { disabled: true } },
    ],
  };
}

/** Approach and departure, shown once for all three charts instead of a legend inside each. */
function LegLegend({ legs }: { legs: string[] }) {
  return (
    <ul className="leg-legend" aria-label="Legend">
      {legs.map((leg) => (
        <li key={leg}>
          <span className={`leg-swatch leg-swatch-${leg}`} aria-hidden="true" />
          {legLabel(leg)}
        </li>
      ))}
    </ul>
  );
}

/** Selected range is pressed, not disabled (F18). */
function RangeControl({ value, onChange }: { value: Range; onChange: (r: Range) => void }) {
  return (
    <div className="segmented" role="group" aria-label="Time range">
      {RANGES.map((r) => (
        <button key={r.id} type="button" aria-pressed={r.id === value} onClick={() => onChange(r.id)}>
          {r.label}
        </button>
      ))}
    </div>
  );
}

/** Per-leg traffic series with a rain strip on the same time axis (no dual axis). Core columns only. */
export default function TrafficCharts({
  siteId,
  timezone,
  baselineNote,
}: {
  siteId: string;
  timezone: string | null | undefined;
  baselineNote?: string | null;
}) {
  const [range, setRange] = useState<Range>("24h");
  const [points, setPoints] = useState<TrafficPoint[] | null>(null);
  const [weather, setWeather] = useState<WeatherSeriesPoint[] | null>(null);
  const [error, setError] = useState("");
  const [rainError, setRainError] = useState("");
  const [now] = useState(() => new Date());

  const from = windowStart(range, now);
  useEffect(() => {
    let live = true;
    setPoints(null);
    setWeather(null);
    setError("");
    setRainError("");
    getTrafficSeries(siteId, from)
      .then((rows) => live && setPoints(rows))
      .catch((e) => live && setError(String(e)));
    // The rain strip is optional: a failed weather fetch shows an error in its block, the traffic charts still render.
    getWeatherSeries(siteId, from)
      .then((rows) => live && setWeather(rows))
      .catch((e) => live && setRainError(String(e)));
    return () => {
      live = false;
    };
  }, [siteId, from]);

  const tz = tzLabel(timezone);
  const offsetMin = utcOffsetMinutes(timezone, now);
  const x = useMemo(() => {
    const shift = offsetMin * 60 * 1000;
    const end = Math.floor(now.getTime() / 1800000) * 1800000 + 1800000;
    return { min: Date.parse(from) + shift, max: end + shift };
  }, [from, now, offsetMin]);
  const rain = useMemo(() => precipitationSeries(weather ?? [], offsetMin), [weather, offsetMin]);
  const charts = useMemo(
    () => (points && points.length ? METRICS.map((m) => ({ ...m, option: lineOption(points, m.field, m.unit, offsetMin, x) })) : []),
    [points, offsetMin, x],
  );
  const rainChart = useMemo(() => (hadRain(rain) ? rainOption(rain, x) : null), [rain, x]);
  const legs = useMemo(() => [...new Set((points ?? []).map((p) => p.leg))].sort(), [points]);
  const group = `traffic-${siteId}`;
  const windowLabel = range === "24h" ? "last 24 hours" : "last 7 days";

  return (
    <Section
      id="traffic"
      title="Traffic"
      note={`Approach and departure legs, ${windowLabel}, times in ${tz}`}
      actions={<RangeControl value={range} onChange={setRange} />}
    >
      {baselineNote && <p className="traffic-provisional">{baselineNote}</p>}
      {error && <Notice tone="error">Couldn't load traffic: {error}</Notice>}
      {!error && points === null && (
        <div className="traffic-stack" aria-busy="true">
          {METRICS.map((m) => (
            <Skeleton key={m.field} height={LINE_HEIGHT} label={`Loading ${m.title.toLowerCase()}`} />
          ))}
          <Skeleton height={RAIN_HEIGHT} label="Loading rain" />
        </div>
      )}
      {points !== null && points.length === 0 && <Notice>No traffic readings in the {windowLabel}.</Notice>}
      {charts.length > 0 && (
        <div className="traffic-stack">
          <LegLegend legs={legs} />
          {charts.map((m) => (
            <Block key={m.field} title={m.title + (m.unit ? ` (${m.unit})` : "")} aside={m.hint}>
              <Chart option={m.option} height={LINE_HEIGHT} group={group} label={`${m.title}, ${windowLabel}`} />
            </Block>
          ))}
          <Block title="Rain (mm)" aside="measured, per half hour">
            {rainError ? (
              <Notice tone="error">Couldn't load rain: {rainError}</Notice>
            ) : weather === null ? (
              <Skeleton height={RAIN_HEIGHT} label="Loading rain" />
            ) : rainChart ? (
              <Chart option={rainChart} height={RAIN_HEIGHT} group={group} label={`Rain, ${windowLabel}`} />
            ) : (
              <Notice>No rain in the {windowLabel}.</Notice>
            )}
          </Block>
        </div>
      )}
    </Section>
  );
}

/** Mean congestion by weekday and local hour, one fixed scale for both legs. Blank cells have no sample yet. */
export function TrafficPattern({ siteId, timezone }: { siteId: string; timezone: string | null | undefined }) {
  const [pattern, setPattern] = useState<PatternCell[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setPattern(null);
    setError("");
    getTrafficPattern(siteId)
      .then((cells) => live && setPattern(cells))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [siteId]);

  const legs = useMemo(() => patternLegs(pattern ?? []), [pattern]);
  const heatmaps = useMemo(() => legs.map((leg) => ({ leg, option: heatmapOption(pattern ?? [], leg) })), [legs, pattern]);
  const tz = tzLabel(timezone);

  return (
    <Section
      id="pattern"
      title="Weekly pattern"
      note={`Mean congestion index by day and hour, last 28 days, ${tz}`}
      actions={<HeatmapLegend />}
    >
      {error && <Notice tone="error">Couldn't load the pattern: {error}</Notice>}
      {!error && pattern === null && <Skeleton height={HEATMAP_HEIGHT} label="Loading weekly pattern" />}
      {pattern !== null && legs.length === 0 && <Notice>No readings in the last 28 days.</Notice>}
      {legs.length > 0 && (
        <div className="pattern-grid">
          {heatmaps.map(({ leg, option }) => (
            <Block key={leg} title={legLabel(leg)}>
              <Chart option={option} height={HEATMAP_HEIGHT} label={`${legLabel(leg)} weekly pattern`} />
            </Block>
          ))}
        </div>
      )}
    </Section>
  );
}

/** Scale outside the plot (F11): what 1.0 and 2.0 mean, plus the "no data" swatch. */
function HeatmapLegend() {
  return (
    <div className="heatmap-legend">
      <span className="heatmap-legend-end">1.0 free flow</span>
      <span className="heatmap-ramp" aria-hidden="true" />
      <span className="heatmap-legend-end">2.0+ twice as slow</span>
      <span className="heatmap-nodata">
        <span className="heatmap-nodata-swatch" aria-hidden="true" />
        no data yet
      </span>
    </div>
  );
}
