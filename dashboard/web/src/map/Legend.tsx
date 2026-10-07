import { BandIndicator } from "../theme/BandIndicator";
import { LatestLeg, Site } from "./api";
import { BAND_RANK, Basis, CONGESTION_BANDS, SPEED_BANDS, legBand } from "./bands";

/** Worst first, so the legend reads in the same order as the site list. */
function Scale({ title, bands }: { title: string; bands: typeof CONGESTION_BANDS }) {
  const ordered = [...bands].sort((a, b) => BAND_RANK[b.band] - BAND_RANK[a.band]);
  return (
    <div className="map-legend-scale">
      <p className="map-legend-title">{title}</p>
      <ul className="map-legend-rows">
        {ordered.map((b) => (
          <li key={b.band}>
            <BandIndicator band={b.band} />
            <span className="map-legend-range">{b.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One row, free flow to jammed: icon and name per band, the ranges in each item's tooltip (and for screen readers). */
function CompactScale({ bases }: { bases: Set<Basis> }) {
  const scales = [
    { on: bases.has("congestion"), name: "Congestion index", bands: CONGESTION_BANDS },
    { on: bases.has("speed"), name: "Speed", bands: SPEED_BANDS },
  ].filter((s) => s.on);
  const ordered = [...CONGESTION_BANDS].sort((a, b) => BAND_RANK[a.band] - BAND_RANK[b.band]);
  return (
    <ul className="map-legend-row">
      {ordered.map(({ band }) => {
        const ranges = scales.map((s) => `${s.name} ${s.bands.find((b) => b.band === band)!.label}`).join("; ");
        return (
          <li key={band} title={ranges}>
            <BandIndicator band={band} />
            <span className="visually-hidden">({ranges})</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Map key for the bands in use: congestion index where the baseline is full, speed where it is still
 * building. Overlaid on the map's corner. `compact` is a single row for small maps, where the full key
 * would cover the legs.
 */
export default function Legend({ sites, latest, compact = false }: { sites: Site[]; latest: Map<string, LatestLeg>; compact?: boolean }) {
  const bases = new Set<Basis>(sites.flatMap((s) => s.legs.map((l) => legBand(latest.get(l.selected_route_id)).basis)));
  const scaled = bases.has("congestion") || bases.has("speed");
  return (
    <aside className={compact ? "map-legend map-legend-compact" : "map-legend"} aria-label="Map key">
      {compact && scaled && <CompactScale bases={bases} />}
      {!compact && bases.has("congestion") && <Scale title="Congestion index (duration ÷ usual)" bands={CONGESTION_BANDS} />}
      {!compact && bases.has("speed") && <Scale title="Speed, while the baseline builds" bands={SPEED_BANDS} />}
      {bases.size === 0 || (bases.size === 1 && bases.has("none")) ? (
        <p className="map-legend-title">
          <BandIndicator band="none" /> No readings yet
        </p>
      ) : (
        bases.has("none") && (
          <p className="map-legend-note">
            <BandIndicator band="none" /> No reading
          </p>
        )
      )}
    </aside>
  );
}
