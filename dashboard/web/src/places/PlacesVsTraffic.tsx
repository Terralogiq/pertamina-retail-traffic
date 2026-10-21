import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { EChartsCoreOption } from "echarts/core";
import { errorText } from "../api";
import { Segmented } from "../map/Segmented";
import { Page } from "../shell/AppShell";
import { CHART_INK } from "../theme/palette";
import Chart from "../traffic/Chart";
import { ViewToggle } from "../traffic/ChartTable";
import { Widget } from "../weather/DemoBadge";
import { PoiAnalysis, PoiLeg, PoiMetric, PoiSite, PoiStat, getPoiAnalysis } from "./analysisApi";
import {
  LEG_OPTIONS,
  METRIC_AXIS,
  METRIC_OPTIONS,
  Point,
  SortKey,
  describe,
  expectedByChance,
  findStat,
  formatInterval,
  formatLoo,
  formatMetric,
  formatP,
  formatRho,
  logCount,
  pointsFor,
  ranks,
  siteLabel,
  sortSites,
  unit,
} from "./analysisModel";
import { formatDate, radiusLabel } from "./model";
import "./PlacesVsTraffic.css";

const SCATTER_HEIGHT = 340;
const SCATTER_GRID = { top: 24, left: 8, right: 32, bottom: 40, containLabel: true };
const SYMBOL_SIZE = 10;
const SYMBOL_SIZE_HOVER = 16;
const MARK_BORDER_WIDTH = 2;

/** Marker shapes by radius index, so a radius is never told apart by colour alone. */
const RADIUS_MARK = ["circle", "square", "triangle"] as const;

/** The caveat. Always on screen: descriptive only, and the dated result of the correction for multiple comparisons. */
export function CaveatBanner({ sites, days, tests }: { sites?: number; days?: number; tests?: number }) {
  return (
    <section className="poi-caveat" role="note" aria-label="Read this first">
      <h2 className="poi-caveat-title">Read this first: exploratory patterns only</h2>
      <p>
        {sites != null && days != null && (
          <>
            {sites} sites, {days} days.{" "}
          </>
        )}
        These are descriptive patterns, not causes. With this few sites only large effects can be detected.
        {tests != null && (
          <>
            {" "}
            {tests} comparisons are shown; about {expectedByChance(tests).toFixed(0)} would look 'significant' by chance.
          </>
        )}
      </p>
      <p>
        <strong>
          In the 14 October 2026 analysis, none of 47 POI measures showed a relationship that survived correction for the number of
          comparisons. With 10 sites a relationship cannot be ruled out either.
        </strong>
      </p>
    </section>
  );
}

/** One row of the summary plot: rho as a marker on -1..+1 with its interval, the exact numbers at the end. */
function SummaryRow({
  stat,
  index,
  selected,
  onSelect,
}: {
  stat: PoiStat;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const pos = (v: number) => `${((v + 1) / 2) * 100}%`;
  const label = radiusLabel(stat.radius_m);
  return (
    <li>
      <button
        type="button"
        className={selected ? "poi-row selected" : "poi-row"}
        aria-pressed={selected}
        onClick={onSelect}
        aria-label={`${label}: rho ${formatRho(stat.rho)}, interval ${formatInterval(stat)}, p ${formatP(stat.p)}`}
      >
        <span className="poi-row-radius">
          <span className={`poi-mark ${RADIUS_MARK[index]} static`} aria-hidden="true" /> {label}
        </span>
        <span className="poi-track" aria-hidden="true">
          {stat.ci_low != null && stat.ci_high != null && (
            <span className="poi-span" style={{ left: pos(stat.ci_low), width: `calc(${pos(stat.ci_high)} - ${pos(stat.ci_low)})` }} />
          )}
          {stat.rho != null && <span className={`poi-mark ${RADIUS_MARK[index]}`} style={{ left: pos(stat.rho) }} />}
        </span>
        <span className="poi-row-values num">
          {"ρ"} {formatRho(stat.rho)} <span className="poi-row-p">p {formatP(stat.p)}</span>
        </span>
      </button>
    </li>
  );
}

function SummaryTable({ stats, groups }: { stats: PoiStat[]; groups: PoiAnalysis["groups"] }) {
  const names = Object.fromEntries(groups.map((g) => [g.id, g.label]));
  return (
    <div className="chart-table-wrap">
      <table className="chart-table">
        <thead>
          <tr>
            <th>POI group</th>
            <th>Radius</th>
            <th>{"ρ"}</th>
            <th>95% interval</th>
            <th>p</th>
            <th>Leave-one-out</th>
            <th>n</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((s) => (
            <tr key={`${s.group}-${s.radius_m}`}>
              <td>{names[s.group] ?? s.group}</td>
              <td>{radiusLabel(s.radius_m)}</td>
              <td className="num">{formatRho(s.rho)}</td>
              <td className="num">{formatInterval(s)}</td>
              <td className="num">{formatP(s.p)}</td>
              <td className="num">{formatLoo(s)}</td>
              <td className="num">{s.n}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One row per POI group, one marker per radius, fixed order (not sorted by rho, so it does not advertise the best). */
export function SummaryPlot({
  data,
  group,
  radius,
  onSelect,
}: {
  data: PoiAnalysis;
  group: string;
  radius: number;
  onSelect: (group: string, radius: number) => void;
}) {
  const [mode, setMode] = useState<"chart" | "table">("chart");
  return (
    <Widget title="Rank correlation by POI group">
      <p className="poi-caption">
        Each marker is the Spearman rank correlation ({"ρ"}) between the number of places within a radius and{" "}
        {METRIC_OPTIONS.find((m) => m.value === data.metric)?.label.toLowerCase()}, across sites. The line is the 95% interval. Zero
        means no relationship. Click a row to inspect it.
      </p>
      <ViewToggle mode={mode} onChange={setMode} />
      {mode === "table" ? (
        <SummaryTable stats={data.stats} groups={data.groups} />
      ) : (
        <>
          <div className="poi-axis" aria-hidden="true">
            <span>{"−"}1 (more places, less traffic)</span>
            <span>0</span>
            <span>+1 (more places, more traffic)</span>
          </div>
          <ol className="poi-groups">
            {data.groups.map((g) => (
              <li key={g.id} className="poi-group">
                <h4 className="poi-group-name">{g.label}</h4>
                <ul className="poi-rows">
                  {data.radii.map((r, i) => {
                    const stat = findStat(data.stats, g.id, r);
                    return stat ? (
                      <SummaryRow key={r} stat={stat} index={i} selected={g.id === group && r === radius} onSelect={() => onSelect(g.id, r)} />
                    ) : null;
                  })}
                </ul>
              </li>
            ))}
          </ol>
        </>
      )}
    </Widget>
  );
}

/** ECharts option for the labelled scatter. `ranked` plots rank against rank, which is what Spearman measures. */
export function scatterOption(points: Point[], metric: PoiMetric, ranked: boolean, hover: string | null, sites: PoiSite[]): EChartsCoreOption {
  const xr = ranks(points.map((p) => p.count));
  const yr = ranks(points.map((p) => p.value));
  const data = points.map((p, i) => {
    const toll = p.site.road_class === "toll";
    const hot = p.site.site_id === hover;
    return {
      value: [ranked ? xr[i] : logCount(p.count), ranked ? yr[i] : p.value],
      site: p.site.site_id,
      name: siteLabel(p.site, sites),
      count: p.count,
      metricValue: p.value,
      symbol: toll ? "diamond" : "circle",
      symbolSize: hot ? SYMBOL_SIZE_HOVER : SYMBOL_SIZE,
      // The toll site is a hollow diamond; the others are filled.
      itemStyle: {
        color: toll ? CHART_INK.surface : CHART_INK.text,
        borderColor: CHART_INK.text,
        borderWidth: toll || hot ? MARK_BORDER_WIDTH : 1,
      },
    };
  });
  return {
    animation: false,
    tooltip: {
      trigger: "item",
      formatter: (p: unknown) => {
        const d = (p as { data: { name: string; count: number; metricValue: number } }).data;
        return `${d.name}<br/>${d.count} places listed<br/>${formatMetric(metric, d.metricValue)}`;
      },
    },
    grid: SCATTER_GRID,
    xAxis: ranked
      ? { type: "value", name: "Rank of place count", nameLocation: "middle", nameGap: 28, min: 0, max: points.length + 1, interval: 1 }
      : { type: "log", name: "Places listed + 1 (log scale)", nameLocation: "middle", nameGap: 28, min: 1 },
    yAxis: ranked
      ? { type: "value", name: `Rank of ${METRIC_AXIS[metric].toLowerCase()}`, nameLocation: "end", nameTextStyle: { align: "left" }, min: 0, max: points.length + 1, interval: 1 }
      : { type: "value", name: METRIC_AXIS[metric], nameLocation: "end", nameTextStyle: { align: "left" }, scale: true },
    series: [
      {
        type: "scatter",
        data,
        label: { show: true, position: "top", formatter: (p: unknown) => (p as { data: { name: string } }).data.name, color: CHART_INK.text, fontSize: 11 },
      },
    ],
  };
}

function ScatterWidget({
  data,
  group,
  radiusIndex,
  ranked,
  onRanked,
  hover,
}: {
  data: PoiAnalysis;
  group: string;
  radiusIndex: number;
  ranked: boolean;
  onRanked: (ranked: boolean) => void;
  hover: string | null;
}) {
  const radius = data.radii[radiusIndex];
  const groupLabel = data.groups.find((g) => g.id === group)?.label ?? group;
  const points = useMemo(() => pointsFor(data.sites, group, radiusIndex, data.metric), [data, group, radiusIndex]);
  const option = useMemo(() => scatterOption(points, data.metric, ranked, hover, data.sites), [points, data.metric, ranked, hover, data.sites]);
  const stat = findStat(data.stats, group, radius);
  return (
    <Widget title={`${groupLabel} within ${radiusLabel(radius)}`}>
      <label className="poi-check">
        <input type="checkbox" checked={ranked} onChange={(e) => onRanked(e.target.checked)} />
        Show ranks (what the correlation measures)
      </label>
      {points.length ? (
        <Chart option={option} height={SCATTER_HEIGHT} label={`${groupLabel} within ${radiusLabel(radius)} against ${METRIC_AXIS[data.metric]}, one point per site`} />
      ) : (
        <p className="poi-empty">No site has both a place count and a traffic value.</p>
      )}
      {stat && (
        <>
          <p className="poi-stats num">
            n = {stat.n} &middot; {"ρ"} {formatRho(stat.rho)} &middot; 95% interval {formatInterval(stat)} &middot; p {formatP(stat.p)}{" "}
            &middot; leave-one-out {formatLoo(stat)}
          </p>
          <p className="poi-sentence">{describe(stat, data.stats.length)}</p>
        </>
      )}
      <p className="poi-note">Cities and roads differ more than surroundings do. KM57A is a toll rest area.</p>
    </Widget>
  );
}

/** One mini scatter in unit coordinates: x per panel (log count, or rank), y shared across panels (or rank). */
function Mini({
  points,
  ranked,
  yRange,
  hover,
  onHover,
}: {
  points: Point[];
  ranked: boolean;
  yRange: [number, number];
  hover: string | null;
  onHover: (id: string | null) => void;
}) {
  const xs = points.map((p) => logCount(p.count));
  const xr = ranks(points.map((p) => p.count));
  const yr = ranks(points.map((p) => p.value));
  const lo = Math.log(Math.min(...xs));
  const hi = Math.log(Math.max(...xs));
  return (
    <svg viewBox="0 0 100 70" className="poi-mini-svg" aria-hidden="true">
      {points.map((p, i) => {
        const x = ranked ? unit(xr[i], 1, points.length) : unit(Math.log(xs[i]), lo, hi);
        const y = ranked ? unit(yr[i], 1, points.length) : unit(p.value, yRange[0], yRange[1]);
        const hot = p.site.site_id === hover;
        const toll = p.site.road_class === "toll";
        const cx = 8 + x * 84;
        const cy = 62 - y * 52;
        const props = {
          className: `poi-dot${hot ? " hot" : ""}${toll ? " toll" : ""}`,
          onMouseEnter: () => onHover(p.site.site_id),
          onMouseLeave: () => onHover(null),
        };
        // The toll site is a hollow diamond, as in the main scatter.
        return toll ? (
          <rect key={p.site.site_id} {...props} x={cx - 3} y={cy - 3} width={6} height={6} transform={`rotate(45 ${cx} ${cy})`} />
        ) : (
          <circle key={p.site.site_id} {...props} cx={cx} cy={cy} r={hot ? 3.5 : 2.5} />
        );
      })}
    </svg>
  );
}

/** 6 x 3: every group at every radius, same y metric and shared y axis. The nothing-lines-up-across-radii view. */
export function SmallMultiples({
  data,
  group,
  radius,
  ranked,
  hover,
  onHover,
  onSelect,
}: {
  data: PoiAnalysis;
  group: string;
  radius: number;
  ranked: boolean;
  hover: string | null;
  onHover: (id: string | null) => void;
  onSelect: (group: string, radius: number) => void;
}) {
  const values = data.sites.map((s) => s.metrics[data.metric]).filter((v): v is number => v != null);
  const yRange: [number, number] = [Math.min(...values), Math.max(...values)];
  return (
    <Widget title="Every group at every radius">
      <p className="poi-caption">
        Same traffic metric on the vertical axis of every panel. If a POI mattered, the pattern would repeat across radii.
      </p>
      <div className="poi-multiples">
        <span />
        {data.radii.map((r) => (
          <span key={r} className="poi-multiples-head">
            {radiusLabel(r)}
          </span>
        ))}
        {data.groups.map((g) => (
          <MultiplesRow key={g.id} data={data} group={g} selected={group} radius={radius} yRange={yRange} ranked={ranked} hover={hover} onHover={onHover} onSelect={onSelect} />
        ))}
      </div>
    </Widget>
  );
}

function MultiplesRow({
  data,
  group,
  selected,
  radius,
  yRange,
  ranked,
  hover,
  onHover,
  onSelect,
}: {
  data: PoiAnalysis;
  group: { id: string; label: string };
  selected: string;
  radius: number;
  yRange: [number, number];
  ranked: boolean;
  hover: string | null;
  onHover: (id: string | null) => void;
  onSelect: (group: string, radius: number) => void;
}) {
  return (
    <>
      <span className="poi-multiples-group">{group.label}</span>
      {data.radii.map((r, i) => {
        const stat = findStat(data.stats, group.id, r);
        const on = group.id === selected && r === radius;
        return (
          <button
            key={r}
            type="button"
            className={on ? "poi-mini selected" : "poi-mini"}
            aria-pressed={on}
            aria-label={`${group.label} within ${radiusLabel(r)}: rho ${formatRho(stat?.rho)}`}
            onClick={() => onSelect(group.id, r)}
          >
            <Mini points={pointsFor(data.sites, group.id, i, data.metric)} ranked={ranked} yRange={yRange} hover={hover} onHover={onHover} />
            <span className="poi-mini-rho num">
              {"ρ"} {formatRho(stat?.rho)}
            </span>
          </button>
        );
      })}
    </>
  );
}

/** Per-site profile: traffic metrics and the POI counts at the selected radius, with bars in the count cells. */
export function SiteTable({
  data,
  radiusIndex,
  hover,
  onHover,
}: {
  data: PoiAnalysis;
  radiusIndex: number;
  hover: string | null;
  onHover: (id: string | null) => void;
}) {
  const [sort, setSort] = useState<{ key: SortKey; descending: boolean }>({ key: "city", descending: false });
  const rows = useMemo(() => sortSites(data.sites, sort.key, sort.descending, radiusIndex), [data.sites, sort, radiusIndex]);
  const max = (group: string) => Math.max(1, ...data.sites.map((s) => s.poi?.[group]?.[radiusIndex] ?? 0));
  const header = (key: SortKey, label: string) => (
    <th aria-sort={sort.key === key ? (sort.descending ? "descending" : "ascending") : undefined}>
      <button
        type="button"
        className="poi-sort"
        onClick={() => setSort((s) => ({ key, descending: s.key === key ? !s.descending : key !== "city" }))}
      >
        {label}
      </button>
    </th>
  );
  return (
    <Widget title={`Sites: traffic and places within ${radiusLabel(data.radii[radiusIndex])}`}>
      <div className="chart-table-wrap">
        <table className="chart-table poi-table">
          <thead>
            <tr>
              {header("city", "Site")}
              <th>Road</th>
              {header("delay", "Mean delay")}
              {header("peak", "Peak")}
              {header("busy", "Busy share")}
              {data.groups.map((g) => header(`poi:${g.id}`, g.label))}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <SiteRow key={s.site_id} site={s} label={siteLabel(s, data.sites)} groups={data.groups} radiusIndex={radiusIndex} max={max} hot={s.site_id === hover} onHover={onHover} />
            ))}
          </tbody>
        </table>
      </div>
    </Widget>
  );
}

function busyLabel(s: PoiSite) {
  const { approach, departure } = s.busy_hours;
  return `${formatMetric("busy", s.metrics.busy)} (${approach ?? "n/a"} / ${departure ?? "n/a"} h)`;
}

function SiteRow({
  site,
  label,
  groups,
  radiusIndex,
  max,
  hot,
  onHover,
}: {
  site: PoiSite;
  label: string;
  groups: PoiAnalysis["groups"];
  radiusIndex: number;
  max: (group: string) => number;
  hot: boolean;
  onHover: (id: string | null) => void;
}) {
  return (
    <tr className={hot ? "hot" : undefined} onMouseEnter={() => onHover(site.site_id)} onMouseLeave={() => onHover(null)}>
      <td>
        <Link to={`/site/${encodeURIComponent(site.site_id)}`}>{label}</Link>
      </td>
      <td>{site.road_class === "toll" ? "Toll" : "Urban"}</td>
      <td className="num">{formatMetric("delay", site.metrics.delay)}</td>
      <td className="num">{formatMetric("peak", site.metrics.peak)}</td>
      <td className="num" title="Weekday busy hours as a share of 24; approach / departure hours in brackets">
        {busyLabel(site)}
      </td>
      {groups.map((g) => {
        const count = site.poi?.[g.id]?.[radiusIndex] ?? null;
        return (
          <td key={g.id} className="num poi-bar-cell">
            {count != null && <span className="poi-bar" style={{ width: `${(count / max(g.id)) * 100}%` }} aria-hidden="true" />}
            <span className="poi-bar-value">{count ?? "n/a"}</span>
          </td>
        );
      })}
    </tr>
  );
}

function Footer({ data, radius }: { data: PoiAnalysis; radius: number }) {
  return (
    <p className="poi-footer">
      Places run {data.places_run ? formatDate(data.places_run) : "n/a"}. Traffic window{" "}
      {data.window.from && data.window.to ? `${formatDate(data.window.from)} to ${formatDate(data.window.to)} (UTC)` : "n/a"}.{" "}
      <span title="Google Places Aggregate counts operational places inside the circle. It says nothing about how many people visit them.">
        Counts are places Google lists within {radiusLabel(radius)}, not footfall.
      </span>
    </p>
  );
}

/** Screen: places near each SPBU vs the traffic in front of it. A null result, shown honestly. */
export function PlacesVsTraffic() {
  const [metric, setMetric] = useState<PoiMetric>("delay");
  const [leg, setLeg] = useState<PoiLeg>("both");
  const [excludeToll, setExcludeToll] = useState(false);
  const [radiusIndex, setRadiusIndex] = useState(1);
  const [selectedGroup, setSelectedGroup] = useState("");
  const [ranked, setRanked] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const [data, setData] = useState<PoiAnalysis | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setError("");
    setData(null);
    getPoiAnalysis(metric, leg, excludeToll)
      .then((r) => live && setData(r))
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [metric, leg, excludeToll, attempt]);

  const group = selectedGroup || data?.groups[0]?.id || "";
  const radius = data?.radii[radiusIndex] ?? 1000;
  const select = (g: string, r: number) => {
    setSelectedGroup(g);
    if (data) setRadiusIndex(data.radii.indexOf(r));
  };
  const nSites = data?.sites.length;

  return (
    <Page title="Places vs traffic" context="Does the number of places around an SPBU relate to the traffic in front of it?">
      <div className="poi-stack">
        <CaveatBanner sites={data?.ready ? nSites : undefined} days={data?.ready ? data.days : undefined} tests={data?.ready ? data.stats.length : undefined} />
        <div className="poi-controls">
          <Segmented label="Traffic metric" options={METRIC_OPTIONS} value={metric} onChange={setMetric} />
          <Segmented label="Leg" options={LEG_OPTIONS} value={leg} onChange={setLeg} />
          <Segmented
            label="Radius"
            options={[500, 1000, 3000].map((r, i) => ({ value: String(i), label: radiusLabel(r) }))}
            value={String(radiusIndex)}
            onChange={(v) => setRadiusIndex(Number(v))}
          />
          <label className="poi-check">
            <input type="checkbox" checked={excludeToll} onChange={(e) => setExcludeToll(e.target.checked)} />
            Exclude toll site (KM57A)
          </label>
        </div>
        {error && (
          <div className="poi-error" role="alert">
            <span>Couldn't load the places comparison. {error}</span>
            <button type="button" className="button" onClick={() => setAttempt((a) => a + 1)}>
              Try again
            </button>
          </div>
        )}
        {!data && !error && (
          <div className="poi-loading" aria-busy="true">
            Loading places comparison&hellip;
          </div>
        )}
        {data && !data.ready && (
          <p className="poi-empty" role="status">
            Needs {Math.max(0, data.ready_days - data.days)} more {data.ready_days - data.days === 1 ? "day" : "days"} of traffic: every
            site must have readings on {data.ready_days} local dates before busy hours and correlations are shown ({data.days} so far).
          </p>
        )}
        {data?.ready && (
          <>
            <SummaryPlot data={data} group={group} radius={radius} onSelect={select} />
            <ScatterWidget data={data} group={group} radiusIndex={radiusIndex} hover={hover} ranked={ranked} onRanked={setRanked} />
            <SmallMultiples data={data} group={group} radius={radius} ranked={ranked} hover={hover} onHover={setHover} onSelect={select} />
            <SiteTable data={data} radiusIndex={radiusIndex} hover={hover} onHover={setHover} />
            <Footer data={data} radius={radius} />
          </>
        )}
      </div>
    </Page>
  );
}
