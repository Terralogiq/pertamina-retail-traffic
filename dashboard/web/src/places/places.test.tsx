import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PlacesResponse, PlaceReview } from "./api";
import {
  collapsedHours,
  groupedPoiRows,
  humanStatus,
  relativeDate,
  competitorRows,
  formatDate,
  latestReviews,
  poiRows,
  radiusLabel,
  starCount,
  totalLabel,
} from "./model";
import { Stars } from "./Stars";
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
  it("star count rounds to whole stars within 0-5", () => {
    expect(starCount(4)).toBe(4);
    expect(starCount(4.6)).toBe(5);
    expect(starCount(7)).toBe(5);
    expect(starCount(null)).toBeNull();
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

describe("readable copy", () => {
  it("collapses seven identical days into one line", () => {
    const week = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];
    expect(collapsedHours(week.map((d) => `${d}: Buka 24 jam`))).toBe("Open 24 hours, every day");
    expect(collapsedHours(week.map((d) => `${d}: 06.00–22.00`))).toBe("06.00–22.00, every day");
    expect(collapsedHours([...week.slice(0, 6).map((d) => `${d}: Buka 24 jam`), "Minggu: Tutup"])).toBeNull();
    expect(collapsedHours(["Senin: Buka 24 jam"])).toBeNull();
  });

  it("labels and groups POI types; unknown types go to Other", () => {
    const groups = groupedPoiRows([
      { place_type: "car_repair", counts: [1, 2, 3] },
      { place_type: "atm", counts: [1, 4, 31] },
      { place_type: "zoo", counts: [0, 0, 1] },
    ]);
    expect(groups.map((g) => g.group)).toEqual(["Money", "Vehicles", "Other"]);
    expect(groups[0].rows[0].label).toBe("ATMs");
    expect(groups[2].rows[0].label).toBe("Zoo");
  });

  it("relative review dates and readable business status", () => {
    const now = new Date("2026-10-07T00:00:00Z");
    expect(relativeDate("2026-09-16T00:00:00Z", now)).toBe("3 weeks ago");
    expect(relativeDate("2026-10-06T00:00:00Z", now)).toBe("yesterday");
    expect(relativeDate(null, now)).toBe("");
    expect(humanStatus("CLOSED_TEMPORARILY")).toBe("Closed temporarily");
  });
});

describe("panels", () => {
  it("summary shows rating, count, author, stars, date and text, and no demo badge", () => {
    const html = renderToStaticMarkup(<PlaceSummary details={data.details!} />);
    for (const s of ["4.4", "1,655", "Sari", "2026-09-20", "text Sari"]) expect(html).toContain(s);
    expect(html).not.toContain("demo-only");
  });

  it("review stars are SVGs with a text label; the aggregate's are hidden next to the number", () => {
    const count = (html: string, needle: string) => html.split(needle).length - 1;
    const one = renderToStaticMarkup(<Stars rating={4} />);
    expect(one).toContain('role="img" aria-label="4 of 5 stars"');
    expect(count(one, "<svg")).toBe(5);
    expect(count(one, "star-filled")).toBe(4);
    expect(count(one, "star-empty")).toBe(1);
    expect(count(one, 'aria-hidden="true"')).toBe(5);
    expect(one).not.toMatch(/[★☆]/);
    const hidden = renderToStaticMarkup(<Stars rating={4.4} decorative />);
    expect(hidden).toContain('<span class="review-stars" aria-hidden="true">');
    expect(hidden).not.toContain("aria-label");
    expect(renderToStaticMarkup(<Stars rating={null} />)).not.toContain("<svg");
    expect(renderToStaticMarkup(<Stars rating={null} decorative />)).toBe("");
    const html = renderToStaticMarkup(<PlaceSummary details={data.details!} />);
    expect(count(html, 'aria-label="4 of 5 stars"')).toBe(2); // the two reviews
    expect(count(html, "<svg")).toBe(15); // two reviews + the aggregate
  });

  it("a missing rating prints n/a once, and a present one is read out of 5", () => {
    const count = (html: string, needle: string) => html.split(needle).length - 1;
    const none = renderToStaticMarkup(<PlaceSummary details={{ ...data.details!, rating: null }} />);
    expect(count(none, ">n/a<")).toBe(1);
    expect(none).not.toContain("out of 5");
    expect(renderToStaticMarkup(<PlaceSummary details={data.details!} />)).toContain('<span class="visually-hidden"> out of 5</span>');
  });

  it("hours list every weekday line", () => {
    const html = renderToStaticMarkup(<OpeningHours details={data.details!} />);
    expect(html).toContain("Senin: Buka 24 jam");
    expect(html).toContain("Selasa: Buka 24 jam");
  });

  it("hours: no disclosure when the days differ; one when seven identical days collapse", () => {
    const week = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];
    const varied = renderToStaticMarkup(<OpeningHours details={data.details!} />);
    expect(varied).not.toContain("<details");
    expect(varied).not.toContain("<summary");
    const same = renderToStaticMarkup(
      <OpeningHours details={{ ...data.details!, weekday_descriptions: week.map((d) => `${d}: Buka 24 jam`) }} />,
    );
    expect(same).toContain("<details");
    expect(same).toContain("Open 24 hours, every day");
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
    for (const s of ["500 m", "1 km", "3 km", "ATMs", "Money", ">31<"]) expect(html).toContain(s);
    expect(html).not.toContain(">atm<");
    expect(html).not.toContain("demo-only");
  });
});
