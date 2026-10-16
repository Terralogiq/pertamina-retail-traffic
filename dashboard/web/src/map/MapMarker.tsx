import type { BandId } from "../theme/palette";
import { BandIndicator } from "../theme/BandIndicator";
import { GroupIcon } from "../overview/QueueGroup";
import type { QueueGroup } from "../overview/model";

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

/** "Potential queues" marker: the group's icon (state without colour) plus its short name, or the size of a cluster. */
export function QueueMarker({
  queueGroup,
  text,
  group = false,
  compact = false,
  selected = false,
}: {
  queueGroup: QueueGroup;
  text: string;
  group?: boolean;
  compact?: boolean;
  selected?: boolean;
}) {
  return (
    <span className={markerClass(group, compact, selected)} data-queue-group={queueGroup}>
      <GroupIcon group={queueGroup} />
      <span className={compact && !group ? "visually-hidden" : "map-marker-text"}>{text}</span>
    </span>
  );
}
