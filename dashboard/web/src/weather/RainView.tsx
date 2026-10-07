import type { EChartsOption } from "echarts";
import { useEffect, useState } from "react";
import { Page } from "../shell/AppShell";
import { SERIES } from "../theme/palette";
import { DemoBadge, Widget } from "./DemoBadge";
import { EChart } from "./EChart";
import { RainResponse, RainSplit, ScatterPoint, SiteInfo, getRain, getSites } from "./api";

export type RainSource = "core" | "demo";

const DAY_OPTIONS = [7, 14, 28];

type Names = Record<string, string>;

/** Switch between rain_flag (core) and demo_rain_flag. The demo option carries the badge. */
export function RainToggle({ value, onChange }: { value: RainSource; onChange: (v: RainSource) => void }) {
  return (
    <fieldset style={{ border: 0, padding: 0, display: "flex", gap: 16 }}>
      <label>
        <input type="radio" name="rain-source" checked={value === "core"} onChange={() => onChange("core")} />
        rain_flag (precipitation above 0.1 mm)
      </label>
      <label>
        <input type="radio" name="rain-source" checked={value === "demo"} onChange={() => onChange("demo")} />
        demo_rain_flag (rain condition type)
        <DemoBadge />
      </label>
    </fieldset>
  );
}

/** Mean delay_s in rain vs dry slots per site and leg. Badged only when split by demo_rain_flag. */
export function RainBars({ data, source, names }: { data: RainSplit[]; source: RainSource; names: Names }) {
  const label = (r: RainSplit) => `${names[r.site_id] ?? r.site_id} · ${r.leg}`;
  const option: EChartsOption = {
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => (v == null ? "n/a" : `${Number(v).toFixed(1)} s`),
    },
    legend: { data: ["Rain", "Dry"] },
    grid: { bottom: 110 },
    xAxis: { type: "category", data: data.map(label), axisLabel: { rotate: 40 } },
    yAxis: { type: "value", name: "mean delay (s)" },
    series: [
      { name: "Rain", type: "bar", itemStyle: { color: SERIES.rain }, data: data.map((r) => r.rain.mean_delay_s) },
      { name: "Dry", type: "bar", itemStyle: { color: SERIES.dry }, data: data.map((r) => r.dry.mean_delay_s) },
    ],
  };
  return (
    <Widget title={`Mean delay, rain vs dry (${source === "core" ? "rain_flag" : "demo_rain_flag"})`} demo={source === "demo"}>
      <EChart option={option} height={380} />
      <small>
        Slots per bar (rain / dry): {data.map((r) => `${label(r)} ${r.rain.n}/${r.dry.n}`).join("; ") || "no data"}
      </small>
    </Widget>
  );
}

/** precipitation_mm against congestion_index, both core: no badge. */
export function RainScatter({ points, names }: { points: ScatterPoint[]; names: Names }) {
  const legs: ("approach" | "departure")[] = ["approach", "departure"];
  const option: EChartsOption = {
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        const [mm, ci, site] = (p as unknown as { data: [number, number, string] }).data;
        return `${names[site] ?? site}<br/>${mm.toFixed(1)} mm, congestion ${ci.toFixed(2)}`;
      },
    },
    legend: { data: legs },
    xAxis: { type: "value", name: "precipitation (mm)", min: 0 },
    yAxis: { type: "value", name: "congestion index", scale: true },
    series: legs.map((leg) => ({
      name: leg,
      type: "scatter" as const,
      itemStyle: { color: SERIES[leg] },
      large: true,
      symbolSize: 6,
      data: points.filter((p) => p.leg === leg).map((p) => [p.precipitation_mm, p.congestion_index, p.site_id]),
    })),
  };
  return (
    <Widget title="Precipitation vs congestion index">
      <EChart option={option} height={340} />
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

  useEffect(() => {
    getSites().then(setSites).catch(() => {}); // site names are a nicety
  }, []);

  useEffect(() => {
    let live = true;
    setError("");
    setData(null);
    getRain(days, siteId || undefined)
      .then((r) => live && setData(r))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [days, siteId]);

  const names: Names = Object.fromEntries(sites.map((s) => [s.site_id, s.name]));

  return (
    <Page title="Traffic vs rain">
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 8 }}>
        <label>
          Site{" "}
          <select value={siteId} onChange={(e) => setSiteId(e.target.value)}>
            <option value="">All sites</option>
            {sites.map((s) => (
              <option key={s.site_id} value={s.site_id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Window{" "}
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {DAY_OPTIONS.map((d) => (
              <option key={d} value={d}>
                {d} days
              </option>
            ))}
          </select>
        </label>
        <RainToggle value={source} onChange={setSource} />
      </div>
      {error && <div role="alert">{error}</div>}
      {!data && !error && <div>Loading…</div>}
      {data && (
        <>
          <RainBars data={data[source]} source={source} names={names} />
          <RainScatter points={data.scatter} names={names} />
        </>
      )}
    </Page>
  );
}
