import type { BandId } from "../theme/palette";
import { BandIndicator } from "../theme/BandIndicator";

/**
 * Map marker body: the band's shape (state without colour) plus a short text (the worst delay, or the
 * size of a group). Rendered into an AdvancedMarkerElement's content element.
 */
export function MapMarker({ band, text, group = false, compact = false }: { band: BandId; text: string; group?: boolean; compact?: boolean }) {
  const cls = ["map-marker", group && "map-marker-group", compact && "map-marker-compact"].filter(Boolean).join(" ");
  return (
    <span className={cls} data-band={band}>
      <BandIndicator band={band} compact />
      <span className={compact && !group ? "visually-hidden" : "map-marker-text"}>{text}</span>
    </span>
  );
}
