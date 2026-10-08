import { starCount } from "./model";

const STARS = 5;
// A five-point star in a 24-unit box.
const STAR_PATH = "M12 2.5l2.94 6.1 6.56.9-4.8 4.6 1.2 6.6L12 17.5l-5.9 3.2 1.2-6.6-4.8-4.6 6.56-.9z";

/**
 * A 1-5 rating as drawn stars: filled, then outline-only (the shape tells filled from empty, so colour is
 * not the only signal). Reads as "4 of 5 stars" to a screen reader; `decorative` hides it when the number is next to it.
 */
export function Stars({ rating, decorative = false }: { rating: number | null | undefined; decorative?: boolean }) {
  const n = starCount(rating);
  if (n === null) return <span className="review-stars review-stars-none">n/a</span>;
  const a11y = decorative ? { "aria-hidden": true } : { role: "img", "aria-label": `${n} of ${STARS} stars` };
  return (
    <span className="review-stars" {...a11y}>
      {Array.from({ length: STARS }, (_, i) => (
        <svg key={i} className={i < n ? "star star-filled" : "star star-empty"} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d={STAR_PATH} />
        </svg>
      ))}
    </span>
  );
}
