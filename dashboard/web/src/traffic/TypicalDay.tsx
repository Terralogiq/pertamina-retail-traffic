import { errorText } from "../api";
import { useEffect, useMemo, useState } from "react";
import { Block, Notice, Section, Skeleton } from "../site/Section";
import { SERIES } from "../theme/palette";
import type { DayKind, TypicalDayResponse, TypicalHour, TypicalLeg } from "./api";
import { getTypicalDay } from "./api";
import BusyHours from "./BusyHours";
import Chart from "./Chart";
import { actionHeadline } from "./headlines";
import { TypicalDayTable, ViewToggle } from "./ChartTable";
import { formatDelay, legLabel, tzLabel } from "./model";
import "./TrafficCharts.css";

const CHART_HEIGHT = 220;
const READY_DAYS = 7;
const HOURS = Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, "0"));
const DAY_KINDS: { id: DayKind; label: string }[] = [
  { id: "weekday", label: "Weekday" },
  { id: "weekend", label: "Weekend" },
];

const legColor = (leg: string) => SERIES[leg as "approach" | "departure"] ?? SERIES.approach;

/** How many local dates the profile rests on. The "needs N more days" line is a sample-size note, not a headline. */
export function typicalNote(days: number, ready: boolean): string {
  const base = `Based on ${days} ${days === 1 ? "day" : "days"}.`;
  if (ready) return base;
  const more = Math.max(0, READY_DAYS - days);
  return `${base} Needs ${more} more ${more === 1 ? "day" : "days"}.`;
}

function hourAt(hours: TypicalHour[], hour: number): TypicalHour | undefined {
  return hours.find((item) => item.hour === hour);
}

function bandWidth(hour: TypicalHour | undefined): number | null {
  if (!hour || hour.p25_delay_s == null || hour.p75_delay_s == null) return null;
  return hour.p75_delay_s - hour.p25_delay_s;
}

/**
 * Median delay by hour, one line per leg, with the middle 50% as a band.
 * Hours with n < 4 are a separate, faded line so a thin sample does not draw as a solid reading.
 */
export function typicalChartOption(legs: TypicalLeg[]) {
  const series = legs.flatMap((leg) => {
    const color = legColor(leg.leg);
    const at = (hour: number) => hourAt(leg.hours, hour);
    const base = HOURS.map((_, hour) => at(hour)?.p25_delay_s ?? null);
    const width = HOURS.map((_, hour) => bandWidth(at(hour)));
    const solid = HOURS.map((_, hour) => {
      const item = at(hour);
      return item && !item.faded ? item.median_delay_s : null;
    });
    const faded = HOURS.map((_, hour) => {
      const item = at(hour);
      return item && item.faded ? item.median_delay_s : null;
    });
    return [
      {
        id: `band-base-${leg.leg}`,
        name: `${legLabel(leg.leg)} band`,
        type: "line" as const,
        stack: `band-${leg.leg}`,
        data: base,
        symbol: "none",
        silent: true,
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
        tooltip: { show: false },
      },
      {
        id: `band-${leg.leg}`,
        name: `${legLabel(leg.leg)} middle 50%`,
        type: "line" as const,
        stack: `band-${leg.leg}`,
        data: width,
        symbol: "none",
        silent: true,
        color,
        lineStyle: { opacity: 0 },
        areaStyle: { color, opacity: 0.18 },
        tooltip: { show: false },
      },
      {
        id: `median-${leg.leg}`,
        name: legLabel(leg.leg),
        type: "line" as const,
        data: solid,
        color,
        showSymbol: false,
        connectNulls: false,
        z: 2,
        lineStyle: { width: 2 },
      },
      {
        id: `median-faded-${leg.leg}`,
        name: legLabel(leg.leg),
        type: "line" as const,
        data: faded,
        color,
        showSymbol: true,
        symbolSize: 6,
        connectNulls: false,
        z: 2,
        lineStyle: { width: 2, opacity: 0.35 },
        itemStyle: { opacity: 0.35 },
      },
    ];
  });
  return {
    animation: false,
    tooltip: {
      trigger: "axis" as const,
      formatter: (raw: unknown) => {
        const items = (Array.isArray(raw) ? raw : [raw]) as { dataIndex?: number }[];
        const index = items[0]?.dataIndex;
        if (index == null) return "";
        return legs
          .map((leg) => {
            const hour = hourAt(leg.hours, index);
            const name = legLabel(leg.leg);
            if (!hour || hour.median_delay_s == null) return `${name}: n/a · n=${hour?.n ?? 0}`;
            const thin = hour.faded ? " · thin sample" : "";
            return `${name}: ${formatDelay(hour.median_delay_s)} · middle 50% ${formatDelay(hour.p25_delay_s)} to ${formatDelay(hour.p75_delay_s)} · n=${hour.n}${thin}`;
          })
          .join("<br/>");
      },
    },
    grid: { left: 52, right: 16, top: 12, bottom: 24 },
    xAxis: { type: "category" as const, data: HOURS, axisLabel: { interval: 2 } },
    yAxis: { type: "value" as const, scale: true, splitNumber: 3, name: "s" },
    series,
  };
}

/** 24 local hours. A thin sample (n < 4) is faded and still shows its count. */
export function HourStrip({ leg, hours }: { leg: string; hours: TypicalHour[] }) {
  const byHour = new Map(hours.map((hour) => [hour.hour, hour]));
  return (
    <ol className="hour-strip" aria-label={`${legLabel(leg)} readings per hour`}>
      {HOURS.map((label, hour) => {
        const item = byHour.get(hour);
        const n = item?.n ?? 0;
        const faded = item?.faded ?? true;
        return (
          <li
            key={hour}
            data-hour={hour}
            data-n={n}
            data-faded={faded ? "true" : "false"}
            className={faded ? "hour-tick is-faded" : "hour-tick"}
          >
            <span className="hour-tick-label">{label}</span>
            <span className="hour-tick-n num">{n}</span>
          </li>
        );
      })}
    </ol>
  );
}

function DayKindControl({ value, onChange }: { value: DayKind; onChange: (kind: DayKind) => void }) {
  return (
    <div className="segmented" role="group" aria-label="Day kind">
      {DAY_KINDS.map((kind) => (
        <button key={kind.id} type="button" aria-pressed={kind.id === value} onClick={() => onChange(kind.id)}>
          {kind.label}
        </button>
      ))}
    </div>
  );
}

/** Weekday or weekend profile: readiness, the median chart, and the per-hour counts. */
export function TypicalDayBody({ data, dayKind }: { data: TypicalDayResponse; dayKind: DayKind }) {
  const legs = useMemo(
    () => data.legs.filter((leg) => leg.day_kind === dayKind).sort((a, b) => a.leg.localeCompare(b.leg)),
    [data, dayKind],
  );
  const option = useMemo(() => (legs.length ? typicalChartOption(legs) : null), [legs]);
  const [view, setView] = useState<"chart" | "table">("chart");
  const kindLabel = dayKind === "weekday" ? "weekday" : "weekend";

  return (
    <div className="traffic-stack">
      <p className="traffic-headline">{actionHeadline(data.ready, legs, dayKind)}</p>
      <p className="typical-readiness">{typicalNote(data.days, data.ready)}</p>
      {data.ready && <BusyHours legs={legs} dayKind={dayKind} />}
      {legs.length === 0 && <Notice>No {kindLabel} readings in the last 28 days.</Notice>}
      {option && (
        <>
          <Block title="Median delay (s)" aside="band is the middle 50%">
            {view === "chart" ? (
              <Chart option={option} height={CHART_HEIGHT} label={`Typical ${kindLabel} delay`} />
            ) : (
              <div className="chart-table-wrap">
                <TypicalDayTable legs={legs} timezone={data.timezone} />
              </div>
            )}
          </Block>
          <div className="site-section-actions">
            <ViewToggle mode={view} onChange={setView} />
          </div>
          <p className="typical-caption">Count under each hour. Faded hours have fewer than 4 readings.</p>
          {legs.map((leg) => (
            <Block key={leg.leg} title={legLabel(leg.leg)}>
              <HourStrip leg={leg.leg} hours={leg.hours} />
            </Block>
          ))}
        </>
      )}
    </div>
  );
}

/** Replaces the day × hour heatmap. Id stays `pattern` so existing section links keep working. */
export default function TypicalDay({ siteId, timezone }: { siteId: string; timezone: string | null | undefined }) {
  const [dayKind, setDayKind] = useState<DayKind>("weekday");
  const [data, setData] = useState<TypicalDayResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setData(null);
    setError("");
    getTypicalDay(siteId)
      .then((body) => live && setData(body))
      .catch((e) => live && setError(errorText(e)));
    return () => {
      live = false;
    };
  }, [siteId]);

  return (
    <Section
      id="pattern"
      title="Typical day"
      note={`Median delay by local hour, last 28 days, ${tzLabel(timezone)}`}
      actions={<DayKindControl value={dayKind} onChange={setDayKind} />}
    >
      {error && <Notice tone="error">Couldn't load the typical day. {error}</Notice>}
      {!error && data === null && <Skeleton height={CHART_HEIGHT} label="Loading typical day" />}
      {data && <TypicalDayBody data={data} dayKind={dayKind} />}
    </Section>
  );
}
