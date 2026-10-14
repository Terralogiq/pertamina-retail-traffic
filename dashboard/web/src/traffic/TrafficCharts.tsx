import { errorText } from "../api";
import { useEffect, useMemo, useState } from "react";
import { Block, Notice, Section, Skeleton } from "../site/Section";
import { CHART_INK, SERIES } from "../theme/palette";
import { WeatherSeriesPoint, getWeatherSeries } from "../weather/api";
import { TrafficPoint, TypicalDayResponse, getTrafficSeries, getTypicalDay } from "./api";
import Chart from "./Chart";
import { TrafficTable, ViewToggle } from "./ChartTable";
import { trafficHeadline } from "./headlines";
import type { Site } from "../map/api";
import {
  DelayDatum,
  Range,
  delaySeries,
  delayTooltipText,
  hadRain,
  legLabel,
  precipitationSeries,
  tzLabel,
  utcOffsetMinutes,
  windowStart,
} from "./model";
import "./TrafficCharts.css";

const LINE_HEIGHT = 200;
const RAIN_HEIGHT = 96;
// Same plot inset on every time chart, so the rain strip lines up under the traffic line.
const GRID = { left: 52, right: 16, top: 12, bottom: 24 };
const RANGES: { id: Range; label: string }[] = [
  { id: "24h", label: "24 h" },
  { id: "7d", label: "7 days" },
];

const legColor = (leg: string) => SERIES[leg as "approach" | "departure"] ?? CHART_INK.text;

/** Midnight reads "7 Oct" instead of a bare day number; other ticks are clock times. */
const TIME_LABELS = { day: "{d} {MMM}", hour: "{HH}:{mm}", minute: "{HH}:{mm}" };

interface DelayTip {
  seriesName?: string;
  value?: [number, number | null] | DelayDatum;
  data?: DelayDatum;
}

/** One delay line per leg. Speed and × usual time stay in the tooltip; they are not their own charts. */
export function delayOption(
  points: TrafficPoint[],
  offsetMin: number,
  x: { min: number; max: number },
) {
  const lines = delaySeries(points, offsetMin).map(({ leg, data }) => ({
    name: legLabel(leg),
    type: "line" as const,
    showSymbol: false,
    connectNulls: false,
    data,
    color: legColor(leg),
    lineStyle: { width: 2 },
  }));
  return {
    useUTC: true, // timestamps are pre-shifted to site-local time (see delaySeries)
    animation: false,
    tooltip: {
      trigger: "axis" as const,
      formatter: (raw: unknown) => {
        const items = (Array.isArray(raw) ? raw : [raw]) as DelayTip[];
        return items
          .map((item) => {
            const data = item.data ?? (item.value && "speed_kmh" in item.value ? item.value : undefined);
            const plotted = Array.isArray(item.value) ? item.value[1] : data?.value[1];
            return delayTooltipText(item.seriesName ?? "", plotted ?? null, data?.speed_kmh ?? null, data?.congestion_index ?? null);
          })
          .join("<br/>");
      },
    },
    grid: GRID,
    xAxis: { type: "time" as const, min: x.min, max: x.max, axisLabel: { formatter: TIME_LABELS } },
    yAxis: { type: "value" as const, scale: true, splitNumber: 3 },
    series: lines,
  };
}

function rainOption(rain: [number, number][], x: { min: number; max: number }) {
  return {
    useUTC: true,
    animation: false,
    tooltip: { trigger: "axis" as const, valueFormatter: (v: number) => `${v.toFixed(1)} mm` },
    grid: GRID,
    xAxis: { type: "time" as const, min: x.min, max: x.max, axisLabel: { formatter: TIME_LABELS } },
    yAxis: { type: "value" as const, min: 0, splitNumber: 2 },
    series: [{ name: "Rain", type: "bar" as const, data: rain, barMaxWidth: 6, itemStyle: { color: SERIES.rain } }],
  };
}

/** Approach and departure, shown once for the delay chart instead of a legend inside the plot. */
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

/** Recent delay, one chart, with a rain strip on the same time axis. Core columns only. */
export default function TrafficCharts({
  siteId,
  timezone,
  baselineNote,
  site,
}: {
  siteId: string;
  timezone: string | null | undefined;
  baselineNote?: string | null;
  site?: import("../map/api").Site;
}) {
  const [range, setRange] = useState<Range>("24h");
  const [points, setPoints] = useState<TrafficPoint[] | null>(null);
  const [profile, setProfile] = useState<TypicalDayResponse | null>(null);
  const [weather, setWeather] = useState<WeatherSeriesPoint[] | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");
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
      .catch((e) => live && setError(errorText(e)));
    // The rain strip is optional: a failed weather fetch shows an error in its block, the delay chart still renders.
    getWeatherSeries(siteId, from)
      .then((rows) => live && setWeather(rows))
      .catch((e) => live && setRainError(errorText(e)));
    return () => {
      live = false;
    };
  }, [siteId, from]);

  useEffect(() => {
    let live = true;
    getTypicalDay(siteId)
      .then((body) => live && setProfile(body))
      .catch(() => live && setProfile(null));
    return () => {
      live = false;
    };
  }, [siteId]);

  const weekdayHeadline = trafficHeadline(profile);

  const tz = tzLabel(timezone);
  const offsetMin = utcOffsetMinutes(timezone, now);
  const x = useMemo(() => {
    const shift = offsetMin * 60 * 1000;
    const end = Math.floor(now.getTime() / 1800000) * 1800000 + 1800000;
    return { min: Date.parse(from) + shift, max: end + shift };
  }, [from, now, offsetMin]);
  const rain = useMemo(() => precipitationSeries(weather ?? [], offsetMin), [weather, offsetMin]);
  const delay = useMemo(
    () => (points && points.length ? delayOption(points, offsetMin, x) : null),
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
      {weekdayHeadline && <p className="traffic-headline">{weekdayHeadline}</p>}
      {error && <Notice tone="error">Couldn't load traffic. {error}</Notice>}
      {!error && points === null && (
        <div className="traffic-stack" aria-busy="true">
          <Skeleton height={LINE_HEIGHT} label="Loading delay" />
          <Skeleton height={RAIN_HEIGHT} label="Loading rain" />
        </div>
      )}
      {points !== null && points.length === 0 && <Notice>No traffic readings in the {windowLabel}.</Notice>}
      {delay && (
        <TrafficChartsBody
          delay={delay}
          rainChart={rainChart}
          points={points ?? []}
          weather={weather}
          rainError={rainError}
          legs={legs}
          site={site}
          timezone={timezone}
          group={group}
          windowLabel={windowLabel}
          view={view}
          onViewChange={setView}
        />
      )}
    </Section>
  );
}

interface TrafficChartsBodyProps {
  delay: ReturnType<typeof delayOption>;
  rainChart: ReturnType<typeof rainOption> | null;
  points: TrafficPoint[];
  weather: WeatherSeriesPoint[] | null;
  rainError: string;
  legs: string[];
  site?: Site;
  timezone: string | null | undefined;
  group: string;
  windowLabel: string;
  view: "chart" | "table";
  onViewChange: (mode: "chart" | "table") => void;
}

/** Loaded state of the traffic card: chart/table toggle, delay block, rain block. */
export function TrafficChartsBody({
  delay,
  rainChart,
  points,
  weather,
  rainError,
  legs,
  site,
  timezone,
  group,
  windowLabel,
  view,
  onViewChange,
}: TrafficChartsBodyProps) {
  return (
    <div className="traffic-stack">
      <LegLegend legs={legs} />
      <Block title="Delay (s)" aside="versus free flow">
        {view === "chart" ? (
          <Chart option={delay} height={LINE_HEIGHT} group={group} label={`Delay, ${windowLabel}`} />
        ) : (
          <div className="chart-table-wrap">
            <TrafficTable points={points} timezone={timezone} site={site} />
          </div>
        )}
      </Block>
      <div className="site-section-actions">
        <ViewToggle mode={view} onChange={onViewChange} />
      </div>
      <Block title="Rain (mm)" aside="measured, per half hour">
        {rainError ? (
          <Notice tone="error">Couldn't load rain. {rainError}</Notice>
        ) : weather === null ? (
          <Skeleton height={RAIN_HEIGHT} label="Loading rain" />
        ) : rainChart ? (
          <Chart option={rainChart} height={RAIN_HEIGHT} group={group} label={`Rain, ${windowLabel}`} />
        ) : (
          <Notice>No rain in the {windowLabel}.</Notice>
        )}
      </Block>
    </div>
  );
}
