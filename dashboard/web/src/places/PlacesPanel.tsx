import { useState } from "react";
import { Block, Notice, Section, Skeleton } from "../site/Section";
import type { Load } from "../site/useSiteData";
import { PlaceDetails, PlaceReview, PlacesResponse } from "./api";
import {
  COMPETITOR_RADII,
  POI_RADII,
  collapsedHours,
  competitorRows,
  formatDate,
  groupedPoiRows,
  humanStatus,
  latestReviews,
  longDate,
  poiRows,
  radiusLabel,
  relativeDate,
  stars,
  totalLabel,
} from "./model";
import "./PlacesPanel.css";

/** Height of the loaded Places section, so the skeleton matches what loads into it. */
const PLACES_HEIGHT = 320;

/** One review, clamped to 3 lines until expanded (F21). */
function Review({ review }: { review: PlaceReview }) {
  const [open, setOpen] = useState(false);
  const long = (review.text ?? "").length > 180;
  return (
    <li className="review">
      <p className="review-meta">
        <span className="review-author">{review.author_name ?? "Anonymous"}</span>
        <span className="review-stars" aria-label={review.rating == null ? "No rating" : `${review.rating} of 5 stars`}>
          {stars(review.rating)}
        </span>
        {review.publish_time && (
          <time dateTime={review.publish_time} title={formatDate(review.publish_time)}>
            {relativeDate(review.publish_time)}
          </time>
        )}
      </p>
      {review.text && <p className={open || !long ? "review-text" : "review-text review-text-clamped"}>{review.text}</p>}
      {long && (
        <button type="button" className="review-more" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </li>
  );
}

/** Rating, review count, status and the 5 latest reviews. Places data: no badge. */
export function PlaceSummary({ details }: { details: PlaceDetails }) {
  const reviews = latestReviews(details.reviews);
  const status = [humanStatus(details.business_status), details.open_now == null ? "" : details.open_now ? "Open now" : "Closed now"]
    .filter(Boolean)
    .join(" · ");
  return (
    <Block title="Rating and reviews" aside={status}>
      <p className="rating">
        <span className="rating-value num">{details.rating == null ? "n/a" : details.rating.toFixed(1)}</span>
        <span className="review-stars" aria-hidden="true">
          {stars(details.rating)}
        </span>
        <span className="rating-count">
          {details.user_rating_count == null ? "n/a" : details.user_rating_count.toLocaleString("en-US")} ratings
        </span>
      </p>
      {reviews.length === 0 ? (
        <Notice>No reviews stored.</Notice>
      ) : (
        <ul className="reviews">
          {reviews.map((r, i) => (
            <Review key={i} review={r} />
          ))}
        </ul>
      )}
    </Block>
  );
}

/** Opening hours: one line when every day matches, the per-day list behind a disclosure (F17). */
export function OpeningHours({ details }: { details: PlaceDetails }) {
  const lines = details.weekday_descriptions;
  const collapsed = collapsedHours(lines);
  const list = (
    <ul>
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
  return (
    <Block title="Opening hours">
      {lines.length === 0 ? (
        <Notice>No opening hours stored.</Notice>
      ) : (
        <>
          {collapsed ? (
            <>
              <p className="hours-summary">{collapsed}</p>
              <details className="hours">
                <summary>Daily hours as listed on Google</summary>
                {list}
              </details>
            </>
          ) : (
            <div className="hours">{list}</div>
          )}
        </>
      )}
    </Block>
  );
}

/** Competing gas stations by brand within 1 km / 3 km; `*` marks a capped (lower-bound) total. */
export function Competitors({ data }: { data: PlacesResponse }) {
  const rows = competitorRows(data.competitors);
  return (
    <Block title="Gas stations nearby" aside="by brand, excluding this station">
      {rows.length === 0 ? (
        <Notice>No nearby search stored.</Notice>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Brand</th>
                {COMPETITOR_RADII.map((r) => (
                  <th key={r} scope="col" className="num-col">
                    {radiusLabel(r)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.brand}>
                  <th scope="row">{row.brand}</th>
                  {row.counts.map((n, i) => (
                    <td key={i} className="num-col">
                      {n ?? "–"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                {COMPETITOR_RADII.map((r) => {
                  const t = data.competitor_totals.find((x) => x.radius_m === r);
                  return (
                    <td key={r} className="num-col">
                      {t ? totalLabel(t) : "–"}
                    </td>
                  );
                })}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      <p className="table-note">* The search returns at most 20 places, so a starred total is a lower bound.</p>
    </Block>
  );
}

/** Operational places per type within 500 m / 1 km / 3 km (Places Aggregate), grouped and labelled. */
export function PoiTable({ data }: { data: PlacesResponse }) {
  const groups = groupedPoiRows(poiRows(data.poi));
  return (
    <Block title="Places around the site" aside="operational, by distance">
      {groups.length === 0 ? (
        <Notice>No counts stored.</Notice>
      ) : (
        <div className="table-scroll">
          <table className="data-table data-table-sticky">
            <thead>
              <tr>
                <th scope="col">Type</th>
                {POI_RADII.map((r) => (
                  <th key={r} scope="col" className="num-col">
                    {radiusLabel(r)}
                  </th>
                ))}
              </tr>
            </thead>
            {groups.map((g) => (
              <tbody key={g.group}>
                <tr className="group-row">
                  <th scope="rowgroup" colSpan={POI_RADII.length + 1}>
                    {g.group}
                  </th>
                </tr>
                {g.rows.map((row) => (
                  <tr key={row.place_type}>
                    <th scope="row" title={row.place_type}>
                      {row.label}
                    </th>
                    {row.counts.map((n, i) => (
                      <td key={i} className="num-col">
                        {n ?? "–"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      )}
    </Block>
  );
}

/** Places section of the site page, from the latest stored run (fetched once by the page). */
export function PlacesPanel({ data }: { data: Load<PlacesResponse> }) {
  const note = data && !(data instanceof Error) && data.fetched_at ? `Google Places, refreshed weekly · last run ${longDate(data.fetched_at)}` : undefined;
  return (
    <Section id="places" title="Places" note={note}>
      {data === undefined && <Skeleton height={PLACES_HEIGHT} label="Loading Places" />}
      {data instanceof Error && <Notice tone="error">Couldn't load Places. {data.message}</Notice>}
      {(data === null || (data && !(data instanceof Error) && !data.details)) && (
        <Notice>No Places run stored for this site yet. The profiler runs every Monday at 02:00 WIB.</Notice>
      )}
      {data && !(data instanceof Error) && data.details && (
        <>
          <PlaceSummary details={data.details} />
          <OpeningHours details={data.details} />
          <Competitors data={data} />
          <PoiTable data={data} />
        </>
      )}
    </Section>
  );
}
