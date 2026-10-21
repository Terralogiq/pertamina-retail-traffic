import { Skeleton } from "../site/Section";
import { Load, isReady } from "../site/useSiteData";
import { tzLabel } from "../traffic/model";
import type { AiSummary, SummaryTopic } from "./api";
import "./SummaryCard.css";

/** Height of the placeholder while the page's one summary request is in flight (the first view of a slot waits for generation). */
export const SUMMARY_LOADING_HEIGHT = 72;

/** "15:30" in the site's timezone (UTC when unknown). */
export function clockTime(iso: string, timezone: string | null | undefined): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timezone ?? "UTC",
  }).format(new Date(iso));
}

/**
 * The AI-generated card at the top of a site-page section: the sentences of one topic from the page's summary.
 * Loading shows a skeleton; no summary (null, a failed request, or no sentence for this topic) shows nothing, so the
 * section reads as before. No demo-only badge: no demo_* field feeds the facts (docs/plans/ai-summaries.md, UI labelling).
 */
export function SummaryCard({
  topic,
  data,
  timezone,
}: {
  topic: SummaryTopic;
  data: Load<AiSummary>;
  timezone: string | null | undefined;
}) {
  if (data === undefined) return <Skeleton height={SUMMARY_LOADING_HEIGHT} label="Loading AI summary" />;
  if (!isReady(data)) return null;
  const sentences = data.sentences.filter((s) => s.topic === topic);
  if (sentences.length === 0) return null;
  const tz = tzLabel(timezone);
  return (
    <aside className="ai-summary" aria-label="AI-generated summary">
      <p className="ai-summary-meta">
        <span className="ai-summary-badge">AI-generated</span>
        <span>{data.model}</span>
        <span>
          Data up to {clockTime(data.as_of ?? data.slot_time, timezone)} {tz}
        </span>
        <span>
          generated {clockTime(data.generated_at, timezone)} {tz}
        </span>
      </p>
      <p className="ai-summary-text">{sentences.map((s) => s.text).join(" ")}</p>
      {topic === "review_themes" && (
        <p className="ai-summary-note">Review themes come from a small sample of Google reviews, not all reviews.</p>
      )}
      <details className="ai-summary-source">
        <summary>Source data</summary>
        <p>From {data.sources[topic].join(", ")}.</p>
        <pre>{JSON.stringify(data.facts[topic] ?? null, null, 2)}</pre>
      </details>
    </aside>
  );
}
