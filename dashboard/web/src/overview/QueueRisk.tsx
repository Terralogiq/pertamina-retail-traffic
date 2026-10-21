import { QueueRisk, RISK_LABELS, RISK_LEVEL } from "./model";
import "./QueueRisk.css";

/**
 * Red: a diamond split in two, so the signals read without colour: the left half is filled when the traffic
 * signal is present, the right half when the review signal is. Yellow: a bar. Green: a circle (the shapes of
 * the "moderate" and "free flow" traffic bands). Drawn in the level's ink, on the level's fill.
 */
export function RiskIcon({ risk }: { risk: QueueRisk }) {
  const level = RISK_LEVEL[risk];
  const traffic = risk === "both" || risk === "traffic";
  const reviews = risk === "both" || risk === "reviews";
  return (
    <svg className="queue-icon" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
      {level === "red" && (
        <>
          {traffic && <path d="M6 1 1 6l5 5Z" fill="currentColor" />}
          {reviews && <path d="M6 1l5 5-5 5Z" fill="currentColor" />}
          <path d="M6 1 11 6 6 11 1 6Z" fill="none" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round" />
        </>
      )}
      {level === "yellow" && <rect x="1" y="3.5" width="10" height="5" rx="1.5" fill="currentColor" />}
      {level === "green" && <circle cx="6" cy="6" r="5" fill="currentColor" />}
    </svg>
  );
}

/** Risk icon and label in a pill. */
export function RiskChip({ risk }: { risk: QueueRisk }) {
  return (
    <span className="queue-chip" data-risk={risk} data-level={RISK_LEVEL[risk]}>
      <RiskIcon risk={risk} />
      {RISK_LABELS[risk]}
    </span>
  );
}
