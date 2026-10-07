import type { EChartsOption } from "echarts";
import { useEffect, useState } from "react";
import { Widget } from "./DemoBadge";
import { EChart } from "./EChart";
import { WeatherLatest, WeatherSeriesPoint, getSites, getWeatherLatest, getWeatherSeries } from "./api";
import { localTime, zoneLabel } from "./time";

const fmt = (v: number | null | undefined, unit: string, digits = 1) =>
  v == null ? "n/a" : `${v.toFixed(digits)} ${unit}`;

/** Core fields only (temperature_c, relative_humidity, precipitation_mm, rain_flag, wind_speed_kmh): no badge. */
export function CoreConditions({ now, tz }: { now: WeatherLatest; tz?: string }) {
  return (
    <Widget title="Current conditions">
      <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "2px 12px", margin: 0 }}>
        <dt>Temperature</dt>
        <dd>{fmt(now.temperature_c, "°C")}</dd>
        <dt>Humidity</dt>
        <dd>{fmt(now.relative_humidity, "%", 0)}</dd>
        <dt>Precipitation</dt>
        <dd>{fmt(now.precipitation_mm, "mm")}</dd>
        <dt>Wind</dt>
        <dd>{fmt(now.wind_speed_kmh, "km/h")}</dd>
        <dt>Rain</dt>
        <dd>{now.rain_flag == null ? "n/a" : now.rain_flag ? "yes" : "no"}</dd>
      </dl>
      <small>
        Slot {localTime(now.slot_time, tz)} {zoneLabel(tz)}
      </small>
    </Widget>
  );
}

/** Condition text, icon, type, rain flag and precipitation probability: all demo_*, so badged. */
export function DemoConditions({ now }: { now: WeatherLatest }) {
  return (
    <Widget title="Conditions (Google Weather)" demo>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {now.demo_icon_uri && <img src={`${now.demo_icon_uri}.svg`} alt="" width={48} height={48} />}
        <div>
          <div>{now.demo_condition_text ?? "n/a"}</div>
          <small>{now.demo_condition_type ?? "n/a"}</small>
        </div>
      </div>
      <div>Rain (condition type): {now.demo_rain_flag == null ? "n/a" : now.demo_rain_flag ? "yes" : "no"}</div>
      <div>Chance of rain: {fmt(now.demo_precip_probability, "%", 0)}</div>
    </Widget>
  );
}

function timeAxis(series: WeatherSeriesPoint[], tz?: string) {
  return series.map((p) => localTime(p.slot_time, tz));
}

/** 24 h temperature_c line and precipitation_mm bars: core only, no badge. */
export function WeatherChart({ series, tz }: { series: WeatherSeriesPoint[]; tz?: string }) {
  const option: EChartsOption = {
    tooltip: { trigger: "axis" },
    legend: { data: ["Temperature (°C)", "Precipitation (mm)"] },
    xAxis: { type: "category", data: timeAxis(series, tz), name: zoneLabel(tz) },
    yAxis: [
      { type: "value", name: "°C", scale: true },
      { type: "value", name: "mm", min: 0, splitLine: { show: false } },
    ],
    series: [
      { name: "Temperature (°C)", type: "line", data: series.map((p) => p.temperature_c), showSymbol: false },
      { name: "Precipitation (mm)", type: "bar", yAxisIndex: 1, data: series.map((p) => p.precipitation_mm) },
    ],
  };
  return (
    <Widget title="Last 24 h: temperature and precipitation">
      <EChart option={option} />
    </Widget>
  );
}

/** demo_precip_probability over the last 24 h: demo-only, badged. */
export function PrecipProbabilityChart({ series, tz }: { series: WeatherSeriesPoint[]; tz?: string }) {
  const option: EChartsOption = {
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: timeAxis(series, tz), name: zoneLabel(tz) },
    yAxis: { type: "value", name: "%", min: 0, max: 100 },
    series: [{ name: "Chance of rain (%)", type: "line", data: series.map((p) => p.demo_precip_probability), showSymbol: false }],
  };
  return (
    <Widget title="Last 24 h: chance of rain" demo>
      <EChart option={option} height={180} />
    </Widget>
  );
}

/** Weather block of the site detail page: current conditions plus the 24 h chart. */
export function WeatherPanel({ siteId }: { siteId: string }) {
  const [now, setNow] = useState<WeatherLatest | null | undefined>(undefined); // undefined = loading, null = none
  const [series, setSeries] = useState<WeatherSeriesPoint[]>([]);
  const [tz, setTz] = useState<string | undefined>();
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setError("");
    setNow(undefined);
    Promise.all([getWeatherLatest(), getWeatherSeries(siteId), getSites().catch(() => [])])
      .then(([latest, points, sites]) => {
        if (!live) return;
        setNow(latest.find((w) => w.site_id === siteId) ?? null);
        setSeries(points);
        setTz(sites.find((s) => s.site_id === siteId)?.timezone);
      })
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [siteId]);

  if (error) return <div role="alert">{error}</div>;
  if (now === undefined) return <div>Loading weather…</div>;
  return (
    <div>
      <h2>Weather</h2>
      {now ? (
        <>
          <CoreConditions now={now} tz={tz} />
          <DemoConditions now={now} />
        </>
      ) : (
        <p>No weather slot in the last 2 hours.</p>
      )}
      <WeatherChart series={series} tz={tz} />
      <PrecipProbabilityChart series={series} tz={tz} />
    </div>
  );
}

