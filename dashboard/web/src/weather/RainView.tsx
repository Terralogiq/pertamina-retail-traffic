import { errorText } from "../api";
import type { EChartsOption } from "echarts";
import { useEffect, useMemo, useState } from "react";
import { Page } from "../shell/AppShell";
import { CHART_INK, SERIES } from "../theme/palette";
import { DemoBadge, Widget } from "./DemoBadge";
import { EChart } from "./EChart";
import { RainResponse, RainSplit, ScatterPoint, SiteInfo, getRain, getSites } from "./api";
import "./RainView.css";

export type RainSource = "core" | "demo";

const DAY_OPTIONS = [7, 14, 28];

/** Below this many rain slots a rain mean is shown but flagged: one shower can swing it. */
export const MIN_RAIN_SLOTS = 6;

type Names = Record<string, string>;

const SOURCE_LABEL: Record<RainSource, string> = {
  core: "Measured rain (> 0.1 mm)",
  demo: "Google weather condition",
};

const LEG_LABEL: Record<string, string> = { approach: "Approach", departure: "Departure" };

// Scatter chart layout (ECharts takes pixels).
const SCATTER_HEIGHT = 320;
const SCATTER_GRID = { top: 56, left: 8, right: 16, bottom: 28, containLabel: true };
const SCATTER_SYMBOL_SIZE = 8;
const SCATTER_BORDER_WIDTH = 1;

/** Which slots count as rainy: measured precipitation (core) or Google's condition type (demo-only). */
export function RainToggle({ value, onChange }: { value: RainSource; onChange: (v: RainSource) => void }) {
  return (
    <fieldset className="rain-segmented">
      <legend className="visually-hidden">Rain is</legend>
      {(["core", "demo"] as const).map((s) => (
        <label key={s} className={value === s ? "rain-segment selected" : "rain-segment"}>
          <input type="radio" name="rain-source" checked={value === s} onChange={() => onChange(s)} />
          {SOURCE_LABEL[s]}
          {s === "demo" && <DemoBadge />}
        </label>
      ))}
    </fieldset>
  );
}

function DaysControl({ value, onChange }: { value: number; onChange: (d: number) => void }) {
  return (
    <div className="rain-segmented" role="group" aria-label="Window">
      {DAY_OPTIONS.map((d) => (
        <button
          key={d}
          type="button"
          className={value === d ? "rain-segment selected" : "rain-segment"}
          aria-pressed={value === d}
          onClick={() => onChange(d)}
        >
          {d} days
        </button>
      ))}
    </div>
  );
}

const seconds = (v: number | null) => (v == null ? "n/a" : `${Math.round(v)} s`);

function signedSeconds(v: number) {
  const r = Math.round(v);
  return r > 0 ? `+${r} s` : `${r} s`;
}

/** Rain minus dry, or null when either side is missing. */
export function rainEffect(r: RainSplit): number | null {
  return r.rain.mean_delay_s == null || r.dry.mean_delay_s == null ? null : r.rain.mean_delay_s - r.dry.mean_delay_s;
}

/** Sites ordered by their largest reliable rain effect; sites with no reliable leg go last. */
export function groupBySite(rows: RainSplit[]): { site_id: string; legs: RainSplit[] }[] {
  const bySite = new Map<string, RainSplit[]>();
  for (const r of rows) bySite.set(r.site_id, [...(bySite.get(r.site_id) ?? []), r]);
  const score = (legs: RainSplit[]) => {
    const reliable = legs.filter((l) => l.rain.n >= MIN_RAIN_SLOTS).map(rainEffect).filter((e): e is number => e != null);
    return reliable.length ? Math.max(...reliable) : -Infinity;
  };
  return [...bySite.entries()]
    .map(([site_id, legs]) => ({
      site_id,
      legs: [...legs].sort((a, b) => a.leg.localeCompare(b.leg)),
    }))
    .sort((a, b) => score(b.legs) - score(a.legs) || a.site_id.localeCompare(b.site_id));
}

/** A 0-based scale covering every mean, rounded up to a tidy step. */
export function delayScale(rows: RainSplit[]): { min: number; max: number } {
  const values = rows.flatMap((r) => [r.rain.mean_delay_s, r.dry.mean_delay_s]).filter((v): v is number => v != null);
  const step = 10;
  const max = Math.max(step, Math.ceil(Math.max(0, ...values) / step) * step);
  const min = Math.min(0, Math.floor(Math.min(0, ...values) / step) * step);
  return { min, max };
}

function LegRow({ row, scale }: { row: RainSplit; scale: { min: number; max: number } }) {
  const pos = (v: number) => `${((v - scale.min) / (scale.max - scale.min)) * 100}%`;
  const { rain, dry } = row;
  const thin = rain.n < MIN_RAIN_SLOTS;
  const effect = rainEffect(row);
  const leg = LEG_LABEL[row.leg] ?? row.leg;
  const lo = rain.mean_delay_s != null && dry.mean_delay_s != null ? Math.min(rain.mean_delay_s, dry.mean_delay_s) : null;
  const hi = rain.mean_delay_s != null && dry.mean_delay_s != null ? Math.max(rain.mean_delay_s, dry.mean_delay_s) : null;
  return (
    <li className={thin ? "rain-leg thin" : "rain-leg"}>
      <span className="rain-leg-name">{leg}</span>
      <span className="rain-track" aria-hidden="true">
        {lo != null && hi != null && <span className="rain-span" style={{ left: pos(lo), width: `calc(${pos(hi)} - ${pos(lo)})` }} />}
        {dry.mean_delay_s != null && (
          <span className="rain-dot dry" style={{ left: pos(dry.mean_delay_s) }} title={`Dry: ${seconds(dry.mean_delay_s)} (${dry.n} slots)`} />
        )}
        {rain.mean_delay_s != null && (
          <span className="rain-dot rain" style={{ left: pos(rain.mean_delay_s) }} title={`Rain: ${seconds(rain.mean_delay_s)} (${rain.n} slots)`} />
        )}
      </span>
      <span className="rain-leg-values num">
        <span className="rain-effect">{effect == null ? (rain.n > 0 ? "no dry slots" : "no rain slots") : signedSeconds(effect)}</span>
        <span className="rain-leg-detail">
          {/* The "no rain slots" line above already says it; don't repeat it as "rain n/a". */}
          dry {seconds(dry.mean_delay_s)}
          {rain.mean_delay_s != null && <> · rain {seconds(rain.mean_delay_s)}</>} · n {rain.n}/{dry.n}
        </span>
      </span>
      {thin && rain.n > 0 && <span className="rain-thin-flag">Only {rain.n} rain slot{rain.n === 1 ? "" : "s"}</span>}
    </li>
  );
}

/** Mean delay in rain vs dry slots, per site and leg, as a dot pair on one shared scale. */
export function RainBars({
  data,
  source,
  names,
  cities = {},
}: {
  data: RainSplit[];
  source: RainSource;
  names: Names;
  cities?: Names;
}) {
  const groups = useMemo(() => groupBySite(data), [data]);
  const scale = useMemo(() => delayScale(data), [data]);
  const anyRain = data.some((r) => r.rain.n > 0);
  return (
    <Widget title="Delay with and without rain" demo={source === "demo"}>
      <p className="rain-caption">
        Mean delay against each leg's free-flow baseline. Rain is {SOURCE_LABEL[source].toLowerCase()}. Legs with fewer than{" "}
        {MIN_RAIN_SLOTS} rain slots are shown faded.
      </p>
      <div className="rain-legend" aria-hidden="true">
        <span className="rain-legend-item">
          <span className="rain-dot dry static" /> Dry
        </span>
        <span className="rain-legend-item">
          <span className="rain-dot rain static" /> Rain
        </span>
        <span className="rain-legend-scale num">
          scale {scale.min} to {scale.max} s
        </span>
      </div>
      {!data.length && <p className="rain-empty">No traffic slots in this window.</p>}
      {data.length > 0 && !anyRain && <p className="rain-empty">No rain slots in this window yet, so there is nothing to compare.</p>}
      <ol className="rain-sites">
        {groups.map((g) => (
          <li key={g.site_id} className="rain-site">
            <div className="rain-site-head">
              <span className="rain-site-city">{cities[g.site_id] ?? g.site_id}</span>
              <span className="rain-site-name">{names[g.site_id] ?? g.site_id}</span>
            </div>
            <ul className="rain-legs">
              {g.legs.map((r) => (
                <LegRow key={r.leg} row={r} scale={scale} />
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </Widget>
  );
}

/** Measured precipitation against congestion index, both core: no badge. Dry slots are left out. */
export function RainScatter({ points, names }: { points: ScatterPoint[]; names: Names }) {
  const wet = points.filter((p) => p.precipitation_mm > 0);
  const legs = ["approach", "departure"] as const;
  const option: EChartsOption = {
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        const [mm, ci, site, leg] = (p as unknown as { data: [number, number, string, string] }).data;
        return `${names[site] ?? site} · ${LEG_LABEL[leg] ?? leg}<br/>${mm.toFixed(1)} mm · congestion ${ci.toFixed(2)}`;
      },
    },
    legend: { top: 0, left: 0, data: legs.map((l) => LEG_LABEL[l]), icon: "circle" },
    grid: SCATTER_GRID,
    xAxis: { type: "value", name: "Rain (mm)", nameLocation: "middle", nameGap: 28, min: 0 },
    yAxis: { type: "value", name: "Congestion index", nameLocation: "end", nameGap: 12, nameTextStyle: { align: "left" }, scale: true },
    series: legs.map((leg) => ({
      name: LEG_LABEL[leg],
      type: "scatter" as const,
      symbolSize: SCATTER_SYMBOL_SIZE,
      itemStyle: { color: SERIES[leg], borderColor: CHART_INK.surface, borderWidth: SCATTER_BORDER_WIDTH },
      data: wet.filter((p) => p.leg === leg).map((p) => [p.precipitation_mm, p.congestion_index, p.site_id, p.leg]),
    })),
  };
  return (
    <Widget title="Rain amount vs congestion">
      <p className="rain-caption">Rainy slots only. Congestion index is the leg's travel time over its free-flow baseline (1 = free flow).</p>
      {wet.length ? <EChart option={option} height={SCATTER_HEIGHT} /> : <p className="rain-empty">No measured rain in this window yet.</p>}
    </Widget>
  );
}

/** Screen 3: traffic vs rain. */
export function RainView() {
  const [sites, setSites] = useState<SiteInfo[]>([]);
  const [siteId, setSiteId] = useState("");
  const [days, setDays] = useState(28);
  const [source, setSource] = useState<RainSource>("core");
  const [data, setData] = useState<RainResponse | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    getSites().then(setSites).catch(() => {}); // site names are a nicety
  }, []);

  useEffect(() => {
    let live = true;
    setError("");
    setData(null);
    getRain(days, siteId || undefined)
      .then((r) => live && setData(r))
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [days, siteId, attempt]);

  const names: Names = Object.fromEntries(sites.map((s) => [s.site_id, s.name]));
  const cities: Names = Object.fromEntries(
    sites.flatMap((s) => {
      const city = (s as SiteInfo & { city?: string }).city;
      return city ? [[s.site_id, city]] : [];
    }),
  );

  return (
    <Page
      title="Traffic vs rain"
      context={`Does rain slow the road in front of each SPBU? Last ${days} days.`}
      actions={
        <>
          <label className="rain-select">
            <span className="visually-hidden">Site</span>
            <select value={siteId} onChange={(e) => setSiteId(e.target.value)}>
              <option value="">All sites</option>
              {sites.map((s) => (
                <option key={s.site_id} value={s.site_id}>
                  {cities[s.site_id] ? `${cities[s.site_id]} · ${s.name}` : s.name}
                </option>
              ))}
            </select>
          </label>
          <DaysControl value={days} onChange={setDays} />
          <RainToggle value={source} onChange={setSource} />
        </>
      }
    >
      {error && (
        <div className="rain-error" role="alert">
          <span>Couldn't load the rain comparison. {error}</span>
          <button type="button" className="button" onClick={() => setAttempt((a) => a + 1)}>
            Try again
          </button>
        </div>
      )}
      {!data && !error && (
        <div className="rain-loading" aria-busy="true">
          Loading rain comparison…
        </div>
      )}
      {data && (
        <div className="rain-grid">
          <RainBars data={data[source]} source={source} names={names} cities={cities} />
          <RainScatter points={data.scatter} names={names} />
        </div>
      )}
    </Page>
  );
}
