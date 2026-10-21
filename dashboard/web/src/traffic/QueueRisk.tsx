import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { errorText } from "../api";
import type { Site } from "../map/api";
import { CONFIDENCE_LABELS } from "../overview/model";
import { categoryName } from "../reviews/model";
import { Block, Notice, Section, Skeleton } from "../site/Section";
import type { AlsDayKind, AlsHour, DayKind, QueueRiskSiteDetail } from "./api";
import { getQueueRiskSite } from "./api";
import { ViewToggle } from "./ChartTable";
import { alsHeadline, approachCaption, clock, isMasked, longestRunText, MASKED_TEXT } from "./queueRiskText";
import { formatDelay, tzLabel } from "./model";
import { DayKindControl } from "./TypicalDay";
import "./TrafficCharts.css";
import "./QueueRisk.css";

const STRIP_HEIGHT = 260;
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

function cellLabel(hour: number, item: AlsHour | undefined): string {
  if (!item || item.n === 0 || item.als_pct == null) return `${clock(hour)} no readings`;
  const outlined = item.approach_only_busy ? ", busy before the station only" : "";
  const thin = item.faded ? ", fewer than 4 readings" : "";
  return `${clock(hour)} slower before the station in ${Math.round(item.als_pct)}% of ${item.n} readings${outlined}${thin}`;
}

/** 24 cells. Fill is the share of readings slower before the station than after it; an outline is a busy hour on that side only. */
export function AlsStrip({ hours }: { hours: AlsHour[] }) {
  const byHour = new Map(hours.map((hour) => [hour.hour, hour]));
  return (
    <>
      <ol className="busy-strip als-strip" aria-label="Share of readings slower before the station, per hour">
        {HOURS.map((hour) => {
          const item = byHour.get(hour);
          const label = cellLabel(hour, item);
          const classes = ["busy-cell", "als-cell"];
          if (item?.faded ?? true) classes.push("is-faded");
          if (item?.approach_only_busy) classes.push("is-outlined");
          return (
            <li
              key={hour}
              data-hour={hour}
              data-n={item?.n ?? 0}
              data-faded={(item?.faded ?? true) ? "true" : "false"}
              data-outlined={item?.approach_only_busy ? "true" : "false"}
              className={classes.join(" ")}
              style={{ "--share": (item?.als_pct ?? 0) / 100 } as CSSProperties}
              title={label}
              aria-label={label}
            />
          );
        })}
      </ol>
      <ol className="busy-ticks" aria-hidden="true">
        {HOURS.map((hour) => (
          <li key={hour} className="hour-tick-label">
            {hour % 6 === 0 ? clock(hour).slice(0, 2) : ""}
          </li>
        ))}
      </ol>
    </>
  );
}

/** The same hours as the strip, as numbers. */
export function AlsTable({ hours }: { hours: AlsHour[] }) {
  const rows = hours.filter((h) => h.n > 0);
  return (
    <table className="chart-table">
      <thead>
        <tr>
          <th>Hour</th>
          <th>Slower before the station</th>
          <th>Busy before the station only</th>
          <th>Median approach delay</th>
          <th>n</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((h) => (
          <tr key={h.hour} className={h.faded ? "is-faded" : undefined}>
            <td className="num">{clock(h.hour)}</td>
            <td className="num">{h.als_pct == null ? "-" : `${Math.round(h.als_pct)}%`}</td>
            <td>{h.approach_only_busy ? "Yes" : "No"}</td>
            <td className="num">{formatDelay(h.approach_median_delay_s)}</td>
            <td className="num">{h.n}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Confidence({ entry }: { entry: QueueRiskSiteDetail }) {
  const confidence = entry.confidence;
  if (!confidence) return null;
  return (
    <p className="queue-confidence">
      <span className="confidence-chip" data-level={confidence.level}>
        Confidence: {CONFIDENCE_LABELS[confidence.level]}
      </span>
      <span className="queue-confidence-reason">{confidence.reason}.</span>
    </p>
  );
}

/** Pointer to the Review themes panel below on the same page. Counts live there, not here. */
function ReviewsPointer() {
  return (
    <p className="queue-reviews">
      Reviews on “{categoryName("antrian")}” and “{categoryName("keamanan_lalu_lintas")}” are counted in{" "}
      <a href="#review-themes">Review themes</a> (sampled reviews, weak evidence).
    </p>
  );
}

/** The content of the card for a loaded site: masked, or headline, strip, facts and confidence. */
export function QueueRiskBody({
  entry,
  site,
  dayKind,
  view,
  onViewChange,
}: {
  entry: QueueRiskSiteDetail;
  site?: Site;
  dayKind: DayKind;
  view: "chart" | "table";
  onViewChange: (view: "chart" | "table") => void;
}) {
  const caption = <p className="typical-caption">{approachCaption(site?.road_class)}</p>;
  if (isMasked(entry)) {
    return (
      <div className="traffic-stack">
        <p className="traffic-headline">{MASKED_TEXT}</p>
        {caption}
        <ReviewsPointer />
      </div>
    );
  }
  const kind: AlsDayKind | undefined = entry.day_kinds.find((k) => k.day_kind === dayKind);
  return (
    <div className="traffic-stack">
      <p className="traffic-headline">{alsHeadline(entry, dayKind)}</p>
      {kind && (
        <>
          <Block title="Slower before the station, by hour" aside="fill = share of readings · outline = busy before the station only">
            {view === "chart" ? (
              <AlsStrip hours={kind.hours} />
            ) : (
              <div className="chart-table-wrap">
                <AlsTable hours={kind.hours} />
              </div>
            )}
          </Block>
          <div className="site-section-actions">
            <ViewToggle mode={view} onChange={onViewChange} />
          </div>
          <p className="typical-caption">Faded hours have fewer than 4 readings.</p>
        </>
      )}
      <dl className="queue-facts">
        <div>
          <dt>Days with 2 h or more slower before the station</dt>
          <dd className="num">
            {entry.days_with_2h_als} of {entry.full_days}
          </dd>
        </div>
        <div>
          <dt>Median approach delay in those slots</dt>
          <dd className="num">{formatDelay(entry.als_median_delay_s)}</dd>
        </div>
        <div>
          <dt>Longest run</dt>
          <dd className="num">{longestRunText(entry.longest_run_h)}</dd>
        </div>
      </dl>
      <Confidence entry={entry} />
      {caption}
      <ReviewsPointer />
    </div>
  );
}

/** Queue risk (approach) card of the site page: fetches its own data once the page has mounted it for a known site. */
export default function QueueRisk({
  siteId,
  timezone,
  site,
}: {
  siteId: string;
  timezone: string | null | undefined;
  site?: Site;
}) {
  const [dayKind, setDayKind] = useState<DayKind>("weekday");
  const [view, setView] = useState<"chart" | "table">("chart");
  const [state, setState] = useState<{ siteId: string; entry: QueueRiskSiteDetail | null | Error | undefined }>({
    siteId,
    entry: undefined,
  });

  useEffect(() => {
    let live = true;
    setState({ siteId, entry: undefined });
    getQueueRiskSite(siteId)
      .then((body) => live && setState({ siteId, entry: body.sites[0] ?? null }))
      .catch((e) => live && setState({ siteId, entry: e instanceof Error ? e : new Error(errorText(e)) }));
    return () => {
      live = false;
    };
  }, [siteId]);

  const entry = state.siteId === siteId ? state.entry : undefined; // never the previous site's strip under the new heading
  const masked = entry != null && !(entry instanceof Error) && isMasked(entry);
  return (
    <Section
      id="queue-risk"
      title="Queue risk (approach)"
      note={`Slower before the station than after it, last 28 days, ${tzLabel(timezone)}`}
      actions={masked ? undefined : <DayKindControl value={dayKind} onChange={setDayKind} />}
    >
      {entry === undefined && <Skeleton height={STRIP_HEIGHT} label="Loading queue risk" />}
      {entry instanceof Error && <Notice tone="error">Couldn't load queue risk. {entry.message}</Notice>}
      {entry === null && <Notice>No readings for both legs of this station in the last 28 days.</Notice>}
      {entry && !(entry instanceof Error) && (
        <QueueRiskBody entry={entry} site={site} dayKind={dayKind} view={view} onViewChange={setView} />
      )}
    </Section>
  );
}
