import { errorText } from "../api";
import type { EChartsOption } from "echarts";
import { useEffect, useState } from "react";
import { Block, Notice, Section, Skeleton } from "../site/Section";
import type { Load } from "../site/useSiteData";
import { SERIES } from "../theme/palette";
import { DemoBadge } from "./DemoBadge";
import { EChart } from "./EChart";
import { WeatherLatest, WeatherSeriesPoint, getWeatherSeries } from "./api";
import { localTime, zoneLabel } from "./time";
import "./WeatherPanel.css";

const CHART_HEIGHT = 160;
/** Height of the current-conditions block, so the skeleton matches what loads into it. */
const NOW_HEIGHT = 136;
const GRID = { left: 44, right: 12, top: 12, bottom: 24 };

const fmt = (v: number | null | undefined, unit: string, digits = 1) =>
  v == null ? "n/a" : `${v.toFixed(digits)} ${unit}`;
const yesNo = (v: boolean | null | undefined) => (v == null ? "n/a" : v ? "Yes" : "No");

/** Core fields only (temperature_c, relative_humidity, precipitation_mm, rain_flag, wind_speed_kmh): no badge. */
export function CoreConditions({ now, tz }: { now: WeatherLatest; tz?: string }) {
  return (
    <div className="weather-now">
      <p className="weather-temp num">{fmt(now.temperature_c, "°C")}</p>
      <dl className="weather-facts">
        <div>
          <dt>Humidity</dt>
          <dd className="num">{fmt(now.relative_humidity, "%", 0)}</dd>
        </div>
        <div>
          <dt>Wind</dt>
          <dd className="num">{fmt(now.wind_speed_kmh, "km/h", 0)}</dd>
        </div>
        <div>
          <dt>Rain</dt>
          <dd className="num">
            {yesNo(now.rain_flag)}
            {now.precipitation_mm ? ` · ${fmt(now.precipitation_mm, "mm")}` : ""}
          </dd>
        </div>
      </dl>
      <p className="weather-slot">
        Reading at <time dateTime={now.slot_time}>{localTime(now.slot_time, tz)}</time> {zoneLabel(tz)}
      </p>
    </div>
  );
}

/** Condition text, icon, type, rain flag and precipitation probability: all demo_*, so badged. */
export function DemoConditions({ now }: { now: WeatherLatest }) {
  return (
    <Block title="Google Weather condition" aside={<DemoBadge />}>
      <div className="weather-condition">
        {now.demo_icon_uri && <img src={`${now.demo_icon_uri}.svg`} alt="" />}
        {/* The condition code (e.g. LIGHT_RAIN) stays available on hover rather than as a raw enum in the copy. */}
        <p title={now.demo_condition_type ?? undefined}>{now.demo_condition_text ?? "n/a"}</p>
      </div>
      <dl className="weather-facts">
        <div>
          <dt>Rain by condition</dt>
          <dd>{yesNo(now.demo_rain_flag)}</dd>
        </div>
        <div>
          <dt>Chance of rain</dt>
          <dd className="num">{fmt(now.demo_precip_probability, "%", 0)}</dd>
        </div>
      </dl>
    </Block>
  );
}

const timeAxis = (series: WeatherSeriesPoint[], tz?: string) => series.map((p) => localTime(p.slot_time, tz));

/** Last 24 h of temperature_c. Core only, no badge. Rain is charted under Traffic, on the traffic time axis. */
export function WeatherChart({ series, tz }: { series: WeatherSeriesPoint[]; tz?: string }) {
  const option: EChartsOption = {
    animation: false,
    tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "n/a" : `${Number(v).toFixed(1)} °C`) },
    grid: GRID,
    xAxis: { type: "category", data: timeAxis(series, tz), axisLabel: { interval: "auto" } },
    yAxis: { type: "value", scale: true, splitNumber: 3 },
    series: [
      {
        name: "Temperature",
        type: "line",
        data: series.map((p) => p.temperature_c),
        showSymbol: false,
        color: SERIES.temperature,
        lineStyle: { width: 2 },
      },
    ],
  };
  return (
    <Block title="Temperature (°C)" aside={`last 24 hours, ${zoneLabel(tz)}`}>
      <EChart option={option} height={CHART_HEIGHT} />
    </Block>
  );
}

/** demo_precip_probability over the last 24 h: demo-only, badged. */
export function PrecipProbabilityChart({ series, tz }: { series: WeatherSeriesPoint[]; tz?: string }) {
  const option: EChartsOption = {
    animation: false,
    tooltip: { trigger: "axis", valueFormatter: (v) => (v == null ? "n/a" : `${v} %`) },
    grid: GRID,
    xAxis: { type: "category", data: timeAxis(series, tz) },
    yAxis: { type: "value", min: 0, max: 100, splitNumber: 2 },
    series: [
      {
        name: "Chance of rain",
        type: "line",
        data: series.map((p) => p.demo_precip_probability),
        showSymbol: false,
        color: SERIES.rain,
        lineStyle: { width: 2 },
      },
    ],
  };
  return (
    <Block title="Chance of rain (%)" aside={<DemoBadge />}>
      <EChart option={option} height={CHART_HEIGHT} />
    </Block>
  );
}

/** Weather section of the site page. `now` comes from the page's shared fetch; the 24 h series is fetched here. */
export function WeatherPanel({
  siteId,
  timezone,
  now,
}: {
  siteId: string;
  timezone: string | null | undefined;
  now: Load<WeatherLatest>;
}) {
  const [series, setSeries] = useState<WeatherSeriesPoint[] | null>(null);
  const [seriesError, setSeriesError] = useState("");
  const tz = timezone ?? undefined;

  useEffect(() => {
    let live = true;
    setSeries(null);
    setSeriesError("");
    getWeatherSeries(siteId)
      .then((rows) => live && setSeries(rows))
      .catch((e) => live && setSeriesError(errorText(e)));
    return () => {
      live = false;
    };
  }, [siteId]);

  return (
    <Section id="weather" title="Weather">
      {now === undefined && <Skeleton height={NOW_HEIGHT} label="Loading current weather" />}
      {now instanceof Error && <Notice tone="error">Couldn't load the current weather. {now.message}</Notice>}
      {now === null && <Notice>No weather reading in the last 2 hours.</Notice>}
      {now && !(now instanceof Error) && <CoreConditions now={now} tz={tz} />}
      {seriesError && <Notice tone="error">Couldn't load the last 24 hours. {seriesError}</Notice>}
      {!seriesError && series === null && <Skeleton height={CHART_HEIGHT + 32} label="Loading temperature" />}
      {series !== null && series.length > 0 && <WeatherChart series={series} tz={tz} />}
      {now && !(now instanceof Error) && <DemoConditions now={now} />}
      {series !== null && series.length > 0 && <PrecipProbabilityChart series={series} tz={tz} />}
    </Section>
  );
}
