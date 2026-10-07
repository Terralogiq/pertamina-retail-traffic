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

/**
 * Map key for the bands in use: congestion index where the baseline is full, speed where it is still
 * building. Overlaid on the map's corner.
 */
export default function Legend({ sites, latest }: { sites: Site[]; latest: Map<string, LatestLeg> }) {
  const bases = new Set<Basis>(sites.flatMap((s) => s.legs.map((l) => legBand(latest.get(l.selected_route_id)).basis)));
  return (
    <aside className="map-legend" aria-label="Map key">
      {bases.has("congestion") && <Scale title="Congestion index (duration ÷ usual)" bands={CONGESTION_BANDS} />}
      {bases.has("speed") && <Scale title="Speed, while the baseline builds" bands={SPEED_BANDS} />}
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
