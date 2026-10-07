import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PlacesResponse, PlaceReview } from "./api";
import {
  competitorRows,
  formatDate,
  latestReviews,
  poiRows,
  radiusLabel,
  stars,
  totalLabel,
} from "./model";
import { Competitors, OpeningHours, PlaceSummary, PoiTable } from "./PlacesPanel";

const review = (day: number, author: string): PlaceReview => ({
  rating: 4,
  text: `text ${author}`,
  language: "id",
  publish_time: `2026-09-${String(day).padStart(2, "0")}T05:00:00Z`,
  author_name: author,
});

const data: PlacesResponse = {
  site_id: "34.121.03",
  run_id: "run-2",
  fetched_at: "2026-10-07T02:46:13.474034Z",
  details: {
    display_name: "SPBU 34.121.03",
    rating: 4.4,
    user_rating_count: 1655,
    business_status: "OPERATIONAL",
    open_now: true,
    weekday_descriptions: ["Senin: Buka 24 jam", "Selasa: Buka 24 jam"],
    reviews: [review(20, "Sari"), review(10, "Budi")],
  },
  competitors: [
    { radius_m: 1000, brand: "Pertamina", count: 0 },
    { radius_m: 1000, brand: "Shell", count: 1 },
    { radius_m: 3000, brand: "Pertamina", count: 5 },
    { radius_m: 3000, brand: "Shell", count: 2 },
  ],
  competitor_totals: [
    { radius_m: 1000, total: 1, capped: false },
    { radius_m: 3000, total: 19, capped: true },
  ],
  poi: [
    { place_type: "atm", radius_m: 500, count: 1 },
    { place_type: "atm", radius_m: 1000, count: 4 },
    { place_type: "atm", radius_m: 3000, count: 31 },
    { place_type: "cafe", radius_m: 500, count: 0 },
  ],
};

describe("helpers", () => {
  it("stars", () => {
    expect(stars(4)).toBe("★★★★☆");
    expect(stars(4.6)).toBe("★★★★★");
    expect(stars(null)).toBe("n/a");
  });

  it("formatDate is the UTC calendar day", () => {
    expect(formatDate("2026-09-20T23:30:00Z")).toBe("2026-09-20");
    expect(formatDate(null)).toBe("");
  });

  it("radiusLabel", () => {
    expect([500, 1000, 3000].map(radiusLabel)).toEqual(["500 m", "1 km", "3 km"]);
  });

  it("latestReviews sorts newest first and keeps 5", () => {
    const many = [1, 5, 3, 9, 7, 2, 8].map((d) => review(d, `u${d}`));
    expect(latestReviews(many).map((r) => r.author_name)).toEqual(["u9", "u8", "u7", "u5", "u3"]);
    expect(latestReviews([{ ...review(1, "none"), publish_time: null }, review(2, "dated")])[0].author_name).toBe(
      "dated",
    );
  });

  it("totalLabel marks a capped total with *", () => {
    expect(totalLabel({ radius_m: 3000, total: 19, capped: true })).toBe("19*");
    expect(totalLabel({ radius_m: 1000, total: 7, capped: false })).toBe("7");
  });

  it("competitorRows pivots brand x [1 km, 3 km]; a missing radius is null", () => {
    expect(competitorRows(data.competitors)).toEqual([
      { brand: "Pertamina", counts: [0, 5] },
      { brand: "Shell", counts: [1, 2] },
    ]);
    expect(competitorRows(data.competitors.slice(0, 2))[0].counts).toEqual([0, null]);
  });

  it("poiRows pivots type x [500 m, 1 km, 3 km]", () => {
    expect(poiRows(data.poi)).toEqual([
      { place_type: "atm", counts: [1, 4, 31] },
      { place_type: "cafe", counts: [0, null, null] },
    ]);
  });
});

describe("panels", () => {
  it("summary shows rating, count, author, stars, date and text, and no demo badge", () => {
    const html = renderToStaticMarkup(<PlaceSummary details={data.details!} />);
    for (const s of ["4.4", "1,655", "Sari", "2026-09-20", "text Sari", "★★★★☆"]) expect(html).toContain(s);
    expect(html).not.toContain("demo-only");
  });

  it("hours list every weekday line", () => {
    const html = renderToStaticMarkup(<OpeningHours details={data.details!} />);
    expect(html).toContain("Senin: Buka 24 jam");
    expect(html).toContain("Selasa: Buka 24 jam");
  });

  it("competitor table headers are 1 km / 3 km and the capped total has the asterisk", () => {
    const html = renderToStaticMarkup(<Competitors data={data} />);
    expect(html).toContain("1 km");
    expect(html).toContain("3 km");
    expect(html).toContain(">19*<");
    expect(html).toContain(">1<");
    expect(html).not.toContain("demo-only");
  });

  it("POI table has the three radius columns", () => {
    const html = renderToStaticMarkup(<PoiTable data={data} />);
    for (const s of ["500 m", "1 km", "3 km", "atm", ">31<"]) expect(html).toContain(s);
    expect(html).not.toContain("demo-only");
  });
});
