import type { BandId } from "../theme/palette";
import { BandIndicator } from "../theme/BandIndicator";
import { RiskIcon } from "../overview/QueueRisk";
import { QueueRisk, RISK_LEVEL } from "../overview/model";

const markerClass = (group: boolean, compact: boolean, selected: boolean) =>
  ["map-marker", group && "map-marker-group", compact && "map-marker-compact", selected && "map-marker-selected"].filter(Boolean).join(" ");

/**
 * Map marker body: the band's shape (state without colour) plus a short text (the worst delay, or the
 * size of a group). Rendered into an AdvancedMarkerElement's content element.
 */
export function MapMarker({
  band,
  text,
  group = false,
  compact = false,
  selected = false,
}: {
  band: BandId;
  text: string;
  group?: boolean;
  compact?: boolean;
  selected?: boolean;
}) {
  return (
    <span className={markerClass(group, compact, selected)} data-band={band}>
      <BandIndicator band={band} compact />
      <span className={compact && !group ? "visually-hidden" : "map-marker-text"}>{text}</span>
    </span>
  );
}

/** "Queue risk" marker: the level's icon (state without colour) plus its short name, or the size of a cluster. */
export function QueueMarker({
  risk,
  text,
  group = false,
  compact = false,
  selected = false,
}: {
  risk: QueueRisk;
  text: string;
  group?: boolean;
  compact?: boolean;
  selected?: boolean;
}) {
  return (
    <span className={markerClass(group, compact, selected)} data-risk={risk} data-level={RISK_LEVEL[risk]}>
      <RiskIcon risk={risk} />
      <span className={compact && !group ? "visually-hidden" : "map-marker-text"}>{text}</span>
    </span>
  );
}
