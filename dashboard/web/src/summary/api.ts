// Client for /api/sites/{site_id}/ai-summary: the AI summary of the current 30-minute slot (docs/plans/ai-summaries.md).
import { getJson } from "../api";

/** One card per topic, each at the top of its site-page section. */
export type SummaryTopic = "traffic" | "weather" | "places" | "review_themes";

export interface SummarySentence {
  topic: SummaryTopic;
  text: string;
}

/**
 * A summary that passed the validator. Times are ISO 8601 UTC: `slot_time` is the slot it serves, `as_of` the latest
 * traffic slot in its facts (null without traffic). `facts` holds what the model saw, one key per topic plus `site`;
 * `sources` lists the tables behind each topic.
 */
export interface AiSummary {
  slot_time: string;
  as_of: string | null;
  generated_at: string;
  model: string;
  model_version: string | null;
  prompt_version: string;
  sentences: SummarySentence[];
  facts: Partial<Record<SummaryTopic | "site", unknown>>;
  sources: Record<SummaryTopic, string[]>;
}

/** `summary` is null when the slot has none: no key, a failed call or an answer the validator rejected. */
export interface AiSummaryResponse {
  site_id: string;
  summary: AiSummary | null;
}

export const getAiSummary = (siteId: string) =>
  getJson<AiSummaryResponse>(`/api/sites/${encodeURIComponent(siteId)}/ai-summary`);
