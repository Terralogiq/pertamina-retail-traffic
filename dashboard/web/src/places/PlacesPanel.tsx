import { useEffect, useState } from "react";
import { Widget } from "../weather/DemoBadge";
import { PlaceDetails, PlacesResponse, getPlaces } from "./api";
import {
  COMPETITOR_RADII,
  POI_RADII,
  competitorRows,
  formatDate,
  latestReviews,
  poiRows,
  radiusLabel,
  stars,
  totalLabel,
} from "./model";

const cell = { textAlign: "right" as const, padding: "2px 10px" };
const head = { ...cell, fontWeight: 600 };
const left = { textAlign: "left" as const, padding: "2px 10px" };

/** Rating, review count, status and the 5 latest reviews. Places data: no badge. */
export function PlaceSummary({ details }: { details: PlaceDetails }) {
  const reviews = latestReviews(details.reviews);
  return (
    <Widget title="Rating and reviews">
      <div>
        <strong>{details.rating == null ? "n/a" : details.rating.toFixed(1)}</strong> {stars(details.rating)}
        {" · "}
        {details.user_rating_count == null ? "n/a" : details.user_rating_count.toLocaleString("en-US")} ratings
      </div>
      <div>
        <small>
          {details.display_name}
          {details.business_status ? ` · ${details.business_status}` : ""}
          {details.open_now == null ? "" : details.open_now ? " · open now" : " · closed now"}
        </small>
      </div>
      {reviews.length === 0 ? (
        <p>No reviews stored.</p>
      ) : (
        <ul style={{ paddingLeft: 18, margin: "8px 0 0" }}>
          {reviews.map((r, i) => (
            <li key={i} style={{ marginBottom: 6 }}>
              <strong>{r.author_name ?? "Anonymous"}</strong> {stars(r.rating)}
              {r.publish_time && <small> · {formatDate(r.publish_time)}</small>}
              {r.text && <div>{r.text}</div>}
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}

/** Regular opening hours, one line per weekday as Places returns them. */
export function OpeningHours({ details }: { details: PlaceDetails }) {
  return (
    <Widget title="Opening hours">
      {details.weekday_descriptions.length === 0 ? (
        <p style={{ margin: 0 }}>No opening hours stored.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {details.weekday_descriptions.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </Widget>
  );
}

/** Competing gas stations by brand within 1 km / 3 km; `*` marks a capped (lower-bound) total. */
export function Competitors({ data }: { data: PlacesResponse }) {
  const rows = competitorRows(data.competitors);
  return (
    <Widget title="Gas stations nearby, by brand">
      {rows.length === 0 ? (
        <p style={{ margin: 0 }}>No nearby search stored.</p>
      ) : (
        <table style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...left, fontWeight: 600 }}>Brand</th>
              {COMPETITOR_RADII.map((r) => (
                <th key={r} style={head}>
                  {radiusLabel(r)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.brand}>
                <td style={left}>{row.brand}</td>
                {row.counts.map((n, i) => (
                  <td key={i} style={cell}>
                    {n ?? "–"}
                  </td>
                ))}
              </tr>
            ))}
            <tr style={{ borderTop: "1px solid #ddd" }}>
              <td style={{ ...left, fontWeight: 600 }}>Total</td>
              {COMPETITOR_RADII.map((r) => {
                const t = data.competitor_totals.find((x) => x.radius_m === r);
                return (
                  <td key={r} style={head}>
                    {t ? totalLabel(t) : "–"}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      )}
      <small>Excludes this station. * = the search returned its maximum of 20 places, so the count is a lower bound.</small>
    </Widget>
  );
}

/** Operational places per type within 500 m / 1 km / 3 km (Places Aggregate). */
export function PoiTable({ data }: { data: PlacesResponse }) {
  const rows = poiRows(data.poi);
  return (
    <Widget title="Points of interest around the site">
      {rows.length === 0 ? (
        <p style={{ margin: 0 }}>No POI counts stored.</p>
      ) : (
        <table style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...left, fontWeight: 600 }}>Type</th>
              {POI_RADII.map((r) => (
                <th key={r} style={head}>
                  {radiusLabel(r)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.place_type}>
                <td style={left}>{row.place_type}</td>
                {row.counts.map((n, i) => (
                  <td key={i} style={cell}>
                    {n ?? "–"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Widget>
  );
}

/** Places block of the site detail page, from the latest stored run. */
export function PlacesPanel({ siteId }: { siteId: string }) {
  const [data, setData] = useState<PlacesResponse | undefined>(undefined); // undefined = loading
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setError("");
    setData(undefined);
    getPlaces(siteId)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [siteId]);

  if (error) return <div role="alert">{error}</div>;
  if (data === undefined) return <div>Loading Places…</div>;
  return (
    <div>
      <h2>Places</h2>
      {data.details ? (
        <>
          <PlaceSummary details={data.details} />
          <OpeningHours details={data.details} />
          <Competitors data={data} />
          <PoiTable data={data} />
          <small>Places data fetched {formatDate(data.fetched_at)}</small>
        </>
      ) : (
        <p>No Places run stored for this site yet.</p>
      )}
    </div>
  );
}
