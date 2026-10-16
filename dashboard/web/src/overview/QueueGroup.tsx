import { GROUP_LABELS, QueueGroup } from "./model";
import "./QueueGroup.css";

/**
 * A diamond split in two, so the group reads without colour: the left half is filled when the traffic signal is
 * present, the right half when the review signal is. Drawn in `currentColor`.
 */
export function GroupIcon({ group }: { group: QueueGroup }) {
  const traffic = group === "potential" || group === "traffic_only";
  const reviews = group === "potential" || group === "reviews_only";
  return (
    <svg className="queue-icon" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      {traffic && <path d="M6 1 1 6l5 5Z" fill="currentColor" />}
      {reviews && <path d="M6 1l5 5-5 5Z" fill="currentColor" />}
      <path d="M6 1 11 6 6 11 1 6Z" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round" />
    </svg>
  );
}

/** Group icon and name in a pill. */
export function GroupChip({ group }: { group: QueueGroup }) {
  return (
    <span className="queue-chip" data-group={group}>
      <GroupIcon group={group} />
      {GROUP_LABELS[group]}
    </span>
  );
}
