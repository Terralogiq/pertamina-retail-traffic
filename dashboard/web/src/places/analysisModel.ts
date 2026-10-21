// Pure helpers behind the Places vs traffic screen.
import type { PoiLeg, PoiMetric, PoiSite, PoiStat } from "./analysisApi";

export const METRIC_OPTIONS: { value: PoiMetric; label: string }[] = [
  { value: "delay", label: "Mean delay" },
  { value: "peak", label: "Peak congestion" },
  { value: "busy", label: "Busy hours" },
];

export const LEG_OPTIONS: { value: PoiLeg; label: string }[] = [
  { value: "both", label: "Both" },
  { value: "approach", label: "Approach" },
  { value: "departure", label: "Departure" },
];

/** Axis title and unit of each traffic metric. */
export const METRIC_AXIS: Record<PoiMetric, string> = {
  delay: "Mean delay (s per km)",
  peak: "Peak congestion (x usual time)",
  busy: "Busy-hour share (weekdays)",
};

/** A tests-by-chance estimate: at 5%, one in 20 comparisons looks 'significant' with nothing there. */
export const expectedByChance = (tests: number) => tests / 20;

const MINUS = "−";

/** "+0.31" / "−0.58" (a real minus sign, so it lines up in tabular figures); "n/a" when missing. */
export function formatRho(rho: number | null | undefined): string {
  if (rho == null) return "n/a";
  const s = Math.abs(rho).toFixed(2);
  return rho < 0 && s !== "0.00" ? `${MINUS}${s}` : `+${s}`;
}

export function formatP(p: number | null | undefined): string {
  if (p == null) return "n/a";
  return p < 0.001 ? "< 0.001" : p.toFixed(p < 0.1 ? 3 : 2);
}

export function formatInterval(stat: Pick<PoiStat, "ci_low" | "ci_high">): string {
  return stat.ci_low == null || stat.ci_high == null ? "n/a" : `${formatRho(stat.ci_low)} to ${formatRho(stat.ci_high)}`;
}

export function formatLoo(stat: Pick<PoiStat, "loo_min" | "loo_max">): string {
  return stat.loo_min == null || stat.loo_max == null ? "n/a" : `${formatRho(stat.loo_min)} to ${formatRho(stat.loo_max)}`;
}

/** A value of the traffic metric as shown in tables and tooltips. */
export function formatMetric(metric: PoiMetric, v: number | null | undefined): string {
  if (v == null) return "n/a";
  if (metric === "delay") return `${Math.round(v)} s/km`;
  if (metric === "peak") return `${v.toFixed(1)}x`;
  return `${Math.round(v * 100)}%`;
}

/** Size words by |rho| only. They describe the size of a pattern, never whether it is real. */
export function strength(rho: number): "weak" | "moderate" | "strong" {
  const a = Math.abs(rho);
  return a < 0.3 ? "weak" : a < 0.6 ? "moderate" : "strong";
}

/**
 * The plain sentence under the scatter. It never says "significant": with these few sites and this many
 * comparisons, an interval clear of zero is still a pattern to re-check, not a finding.
 */
export function describe(stat: PoiStat | undefined, tests: number): string {
  if (!stat || stat.rho == null) return "Not enough variation across sites to compute a correlation.";
  const figures = `ρ ${formatRho(stat.rho)}, compatible with ${formatInterval(stat)}`;
  const spansZero = stat.ci_low == null || stat.ci_high == null || (stat.ci_low <= 0 && stat.ci_high >= 0);
  if (spansZero) return `No clear relationship: ${figures}.`;
  const sign = stat.rho > 0 ? "positive" : "negative";
  return `A ${strength(stat.rho)} ${sign} pattern: ${figures}. About 1 of ${tests} such comparisons would look like this by chance; not corrected.`;
}

export const findStat = (stats: PoiStat[], group: string, radius: number) =>
  stats.find((s) => s.group === group && s.radius_m === radius);

/**
 * City name, with the site id added when another site in `all` is in the same city (two points or links must not read
 * alike), and "(toll)" on the toll site so the reader sees why it is the odd point.
 */
export function siteLabel(s: PoiSite, all: PoiSite[] = []): string {
  const name = s.city ?? s.name;
  const shared = all.some((o) => o.site_id !== s.site_id && (o.city ?? o.name) === name);
  const label = shared ? `${name} ${s.site_id}` : name;
  return s.road_class === "toll" ? `${label} (toll)` : label;
}

export interface Point {
  site: PoiSite;
  count: number;
  value: number;
}

/** Sites that have both the POI count at `radiusIndex` and the traffic metric. */
export function pointsFor(sites: PoiSite[], group: string, radiusIndex: number, metric: PoiMetric): Point[] {
  return sites.flatMap((site) => {
    const count = site.poi?.[group]?.[radiusIndex];
    const value = site.metrics[metric];
    return count == null || value == null ? [] : [{ site, count, value }];
  });
}

/** Average ranks, 1-based; ties share the mean of their ranks (what Spearman measures). */
export function ranks(values: number[]): number[] {
  const order = values.map((v, i) => [v, i] as const).sort((a, b) => a[0] - b[0]);
  const out = new Array<number>(values.length);
  for (let i = 0; i < order.length; ) {
    let j = i;
    while (j + 1 < order.length && order[j + 1][0] === order[i][0]) j++;
    for (let k = i; k <= j; k++) out[order[k][1]] = (i + j) / 2 + 1;
    i = j + 1;
  }
  return out;
}

/** Position of `v` between `lo` and `hi` as 0..1; the middle when the range is empty. */
export const unit = (v: number, lo: number, hi: number) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);

/** Counts are plotted on a log axis; a count of 0 has no log, so every count is shifted up by one. */
export const logCount = (count: number) => count + 1;

export type SortKey = "city" | PoiMetric | `poi:${string}`;

/** The table order for a sort key; missing values go last either way. */
export function sortSites(sites: PoiSite[], key: SortKey, descending: boolean, radiusIndex: number): PoiSite[] {
  const sign = descending ? -1 : 1;
  const text = (s: PoiSite) => siteLabel(s, sites);
  const num = (s: PoiSite) =>
    key === "city" ? null : key.startsWith("poi:") ? (s.poi?.[key.slice(4)]?.[radiusIndex] ?? null) : s.metrics[key as PoiMetric];
  return [...sites].sort((a, b) => {
    if (key === "city") return sign * text(a).localeCompare(text(b));
    const x = num(a);
    const y = num(b);
    if (x == null || y == null) return x == null && y == null ? 0 : x == null ? 1 : -1;
    return sign * (x - y);
  });
}
