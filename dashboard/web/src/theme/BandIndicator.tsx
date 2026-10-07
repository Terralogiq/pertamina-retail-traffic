import { BANDS, BandId } from "./palette";
import "./BandIndicator.css";

/** One shape per band, so the state reads without colour: circle, bar, triangle, octagon, ring. */
function BandIcon({ band }: { band: BandId }) {
  const fill = `var(--band-${band})`;
  return (
    <svg className="band-icon" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      {band === "free" && <circle cx="6" cy="6" r="5" fill={fill} />}
      {band === "moderate" && <rect x="1" y="3.5" width="10" height="5" rx="1.5" fill={fill} />}
      {band === "heavy" && <path d="M6 1 11.2 10.5H0.8Z" fill={fill} />}
      {band === "jam" && <path d="M3.9 0.8h4.2l3.1 3.1v4.2l-3.1 3.1H3.9L0.8 8.1V3.9Z" fill={fill} />}
      {band === "none" && <circle cx="6" cy="6" r="4.25" fill="none" stroke={fill} strokeWidth="1.5" />}
    </svg>
  );
}

/** Band icon plus its label. `compact` keeps the label for screen readers only (use where a legend sits nearby). */
export function BandIndicator({ band, compact = false }: { band: BandId; compact?: boolean }) {
  const { label } = BANDS[band];
  return (
    <span className="band-indicator" data-band={band}>
      <BandIcon band={band} />
      <span className={compact ? "visually-hidden" : "band-label"}>{label}</span>
    </span>
  );
}
