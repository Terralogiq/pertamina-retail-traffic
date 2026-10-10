// Pure helpers behind the Review themes panel.
import type { ThemeCount } from "./api";

/** Readable names for the taxonomy of docs/plans/complaints-analysis.md. */
export const CATEGORY_NAMES: Record<string, string> = {
  antrian: "Queues",
  pelayanan_petugas: "Staff service",
  bbm_kosong: "Fuel out of stock",
  kualitas_bbm: "Fuel quality",
  takaran: "Fill volume",
  pembayaran: "Payment",
  harga: "Price",
  kebersihan: "Cleanliness",
  toilet: "Toilet",
  fasilitas: "Facilities",
  keamanan_lalu_lintas: "Traffic and safety",
  lainnya: "Other",
};

/** "antrian" -> "Queues"; an unknown value becomes "Some new label" rather than disappearing. */
export function categoryName(category: string): string {
  if (category in CATEGORY_NAMES) return CATEGORY_NAMES[category];
  const s = category.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** The largest category total: every bar is scaled to it. At least 1, so an empty list never divides by zero. */
export const maxTotal = (categories: ThemeCount[]) => Math.max(1, ...categories.map((c) => c.recent + c.older));

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-09" -> "Sep 2026" (locale-independent). */
export function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  const name = MONTHS[Number(m) - 1];
  return name ? `${name} ${year}` : month;
}

/** "Queues, Staff service" for a gist's labels. */
export const labelList = (labels: string[]) => labels.map(categoryName).join(", ");

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The sample size behind the bars: "15 stored reviews, 12 with text, 8 labelled." Counts only. */
export const nLine = (r: { n_reviews: number; n_text_reviews: number; n_labelled: number }) =>
  `n = ${plural(r.n_reviews, "stored review", "stored reviews")}, ${r.n_text_reviews} with text, ${r.n_labelled} labelled.`;
