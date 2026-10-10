// Client for /api/sites/{site_id}/review-themes: counts of negative or mixed review topics. No review text, no author.
import { getJson } from "../api";

/** Reviews carrying the topic with sentiment neg or mixed; `recent` = published in the last 12 months. */
export interface ThemeCount {
  category: string;
  recent: number;
  older: number;
}

/** A masked English one-line gist. `month` is "YYYY-MM" of the review date. */
export interface ThemeGist {
  month: string;
  labels: string[];
  gist: string;
}

/**
 * `n_reviews`: every stored review of the site; `n_text_reviews`: those with text; `n_labelled`: those with a label
 * (gemini over manual). `categories` is sorted by total, most first. `gists` holds up to 5, newest first.
 */
export interface ReviewThemesResponse {
  site_id: string;
  n_reviews: number;
  n_text_reviews: number;
  n_labelled: number;
  categories: ThemeCount[];
  gists: ThemeGist[];
}

export const getReviewThemes = (siteId: string) =>
  getJson<ReviewThemesResponse>(`/api/sites/${encodeURIComponent(siteId)}/review-themes`);
