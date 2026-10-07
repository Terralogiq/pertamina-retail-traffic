// Data palette: the one source for colours that carry meaning (map legs, charts, heatmap).
// Brand and chrome colours live in tokens.css; these never double as brand colours.
// Validated with the dataviz validator on #ffffff (light): bands and series each pass all-pairs
// CVD and normal-vision separation; sequential passes the ordinal checks. Colour is never the only
// signal: bands ship with an icon and a label (BandIndicator), series with a legend.

export type BandId = "free" | "moderate" | "heavy" | "jam" | "none";

/** Traffic state of a leg, worst last. `none` = no reading or no basis yet. */
export const BANDS: Record<BandId, { color: string; label: string }> = {
  free: { color: "#1a9e8f", label: "Free flow" },
  moderate: { color: "#e9a400", label: "Moderate" },
  heavy: { color: "#e0602a", label: "Heavy" },
  jam: { color: "#a51d2d", label: "Jammed" },
  none: { color: "#a8a69f", label: "No data" },
};

/** Chart series. One colour, one meaning, on every chart. `dry` is neutral: it is the baseline, not a series. */
export const SERIES = {
  approach: "#4a3aa7",
  departure: "#d0499a",
  rain: "#2a78d6",
  temperature: "#8a5a00",
  dry: "#a8a69f",
} as const;

/** Magnitude ramp (light to dark, one hue) for heatmaps such as congestion by day and hour. */
export const SEQUENTIAL = ["#eea47c", "#e5824f", "#d4612f", "#b0441d", "#842c11"] as const;

/** Chart chrome, read from the tokens.css neutrals so a theme change reaches the charts too. */
export const CHART_INK = {
  text: cssVar("--ink-2", "#4a5564"),
  muted: cssVar("--ink-3", "#6b7684"),
  axis: cssVar("--border-strong", "#c4cad2"),
  grid: cssVar("--surface-sunken", "#e6e9ed"),
  surface: cssVar("--surface-1", "#ffffff"),
} as const;

function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/** Mirrors the data palette into CSS custom properties, so CSS and TS read one source. */
export function applyDataPalette(root: HTMLElement): void {
  for (const [id, band] of Object.entries(BANDS)) root.style.setProperty(`--band-${id}`, band.color);
  for (const [id, color] of Object.entries(SERIES)) root.style.setProperty(`--series-${id}`, color);
  SEQUENTIAL.forEach((color, i) => root.style.setProperty(`--seq-${i + 1}`, color));
}
