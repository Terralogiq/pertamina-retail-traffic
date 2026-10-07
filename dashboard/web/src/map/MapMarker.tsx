import type { BandId } from "../theme/palette";
import { BandIndicator } from "../theme/BandIndicator";

/**
 * Map marker body: the band's shape (state without colour) plus a short text (the worst delay, or the
 * size of a group). Rendered into an AdvancedMarkerElement's content element.
 */
export function MapMarker({ band, text, group = false }: { band: BandId; text: string; group?: boolean }) {
  return (
    <span className={group ? "map-marker map-marker-group" : "map-marker"} data-band={band}>
      <BandIndicator band={band} compact />
      <span className="map-marker-text">{text}</span>
    </span>
  );
}
