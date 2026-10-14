import type { Site } from "../map/api";
import { BANDS } from "../theme/palette";
import type { TrafficPoint, TypicalLeg } from "./api";
import { formatSlot, legBand, legContext } from "../map/bands";
import { formatDelay, legLabel } from "./model";
import "./TrafficCharts.css";

type TableMode = "chart" | "table";

export function ViewToggle({ mode, onChange }: { mode: TableMode; onChange: (mode: TableMode) => void }) {
  return (
    <div className="segmented" role="group" aria-label="View">
      <button type="button" aria-pressed={mode === "chart"} onClick={() => onChange("chart")}>
        Chart
      </button>
      <button type="button" aria-pressed={mode === "table"} onClick={() => onChange("table")}>
        Table
      </button>
    </div>
  );
}

function trafficBand(point: TrafficPoint, site?: Site): string {
  const ctx = site ? legContext(site, point.selected_route_id) : undefined;
  return BANDS[legBand(point, ctx).band].label;
}

export function TrafficTable({
  points,
  timezone,
  site,
}: {
  points: TrafficPoint[];
  timezone: string | null | undefined;
  site?: Site;
}) {
  const rows = [...points].sort((a, b) => Date.parse(b.slot_time) - Date.parse(a.slot_time));
  return (
    <table className="chart-table">
      <thead>
        <tr>
          <th>Time</th>
          <th>Leg</th>
          <th>Delay</th>
          <th>Band</th>
          <th>Speed</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={`${p.selected_route_id}-${p.slot_time}`}>
            <td>{timezone ? formatSlot(p.slot_time, timezone) : p.slot_time}</td>
            <td>{legLabel(p.leg)}</td>
            <td className="num">{formatDelay(p.delay_s)}</td>
            <td>{trafficBand(p, site)}</td>
            <td className="num">{p.speed_kmh == null ? "-" : `${Math.round(p.speed_kmh)} km/h`}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function TypicalDayTable({ legs }: { legs: TypicalLeg[] }) {
  const rows = legs.flatMap((leg) =>
    leg.hours
      .filter((h) => h.median_delay_s != null)
      .map((h) => ({
        leg: leg.leg,
        hour: h.hour,
        median: h.median_delay_s as number,
        p25: h.p25_delay_s,
        p75: h.p75_delay_s,
        n: h.n,
        faded: h.faded,
        busy: h.busy,
      })),
  );
  return (
    <table className="chart-table">
      <thead>
        <tr>
          <th>Hour</th>
          <th>Leg</th>
          <th>Median delay</th>
          <th>Middle 50%</th>
          <th>Busy</th>
          <th>n</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.leg}-${r.hour}`} className={r.faded ? "is-faded" : undefined}>
            <td className="num">{String(r.hour).padStart(2, "0")}:00</td>
            <td>{legLabel(r.leg)}</td>
            <td className="num">{formatDelay(r.median)}</td>
            <td className="num">{r.p25 == null || r.p75 == null ? "-" : `${formatDelay(r.p25)} to ${formatDelay(r.p75)}`}</td>
            <td>{r.busy ? "Yes" : "No"}</td>
            <td className="num">{r.n}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
