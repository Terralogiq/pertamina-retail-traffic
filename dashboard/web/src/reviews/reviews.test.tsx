import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ReviewThemesResponse } from "./api";
import { categoryName, labelList, maxTotal, monthLabel, nLine } from "./model";
import { ReviewThemes } from "./ReviewThemesPanel";

const data: ReviewThemesResponse = {
  site_id: "34.121.03",
  n_reviews: 15,
  n_text_reviews: 12,
  n_labelled: 12,
  categories: [
    { category: "antrian", recent: 4, older: 1 },
    { category: "harga", recent: 1, older: 0 },
    { category: "label_baru", recent: 0, older: 2 },
  ],
  gists: [
    { month: "2026-09", labels: ["antrian", "pelayanan_petugas"], gist: "Long queue at the pump" },
    { month: "2025-11", labels: [], gist: "Rude attendant" },
  ],
};

describe("helpers", () => {
  it("category names are English; an unknown value is still readable", () => {
    expect(categoryName("antrian")).toBe("Queues");
    expect(categoryName("keamanan_lalu_lintas")).toBe("Traffic and safety");
    expect(categoryName("label_baru")).toBe("Label baru");
    expect(labelList(["antrian", "harga"])).toBe("Queues, Price");
  });

  it("bars scale to the largest total, never below 1", () => {
    expect(maxTotal(data.categories)).toBe(5);
    expect(maxTotal([])).toBe(1);
  });

  it("month label and n line", () => {
    expect(monthLabel("2026-09")).toBe("Sep 2026");
    expect(monthLabel("bad")).toBe("bad");
    expect(nLine(data)).toBe("n = 15 stored reviews, 12 with text, 12 labelled.");
    expect(nLine({ n_reviews: 1, n_text_reviews: 0, n_labelled: 0 })).toContain("1 stored review,");
  });
});

describe("panel", () => {
  const html = renderToStaticMarkup(<ReviewThemes data={data} />);
  const text = html.replace(/<[^>]+>/g, " ");

  it("shows a bar per category with the counts written out, in English", () => {
    for (const s of ["Queues", "Price", "Label baru", "4 recent · 1 older", "1 recent · 0 older", "0 recent · 2 older"]) {
      expect(text).toContain(s);
    }
    expect(text).not.toContain("antrian");
    expect(html.split('class="theme-row"').length - 1).toBe(3);
  });

  it("carries the demo-only label with the sampling note, and the n line", () => {
    expect(html).toContain('class="demo-badge"');
    expect(text).toContain("sampled, ≤15 reviews per window");
    expect(text).toContain("n = 15 stored reviews, 12 with text, 12 labelled.");
  });

  it("lists the gists with month and readable labels", () => {
    for (const s of ["Sep 2026", "Queues, Staff service", "Long queue at the pump", "Nov 2025", "Rude attendant"]) {
      expect(text).toContain(s);
    }
  });

  it("prints no percentage and no rank", () => {
    expect(text).not.toContain("%");
    expect(text).not.toMatch(/rank|#1|vs\.? other sites/i);
  });

  it("empty state when nothing is labelled: no chart, no gists", () => {
    const empty = renderToStaticMarkup(<ReviewThemes data={{ ...data, n_labelled: 0, categories: [], gists: [] }} />);
    expect(empty).toContain("No reviews labelled for this site yet.");
    expect(empty).not.toContain("theme-row");
    expect(empty).toContain("n = 15 stored reviews");
  });

  it("labelled but no negative or mixed review says so", () => {
    const none = renderToStaticMarkup(<ReviewThemes data={{ ...data, categories: [], gists: [] }} />);
    expect(none).toContain("No negative or mixed review in the labelled sample.");
    expect(none).not.toContain("Recent complaints");
  });
});
