import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AiSummary } from "./api";
import { SummaryCard, clockTime } from "./SummaryCard";

const summary: AiSummary = {
  slot_time: "2026-10-14T08:30:00Z",
  as_of: "2026-10-14T08:30:00Z",
  generated_at: "2026-10-14T08:41:00Z",
  model: "gemini-3.8-flash",
  model_version: "gemini-3.8-flash-001",
  prompt_version: "s5",
  sentences: [
    { topic: "traffic", text: "The approach leg had 4 slow slots." },
    { topic: "traffic", text: "The departure leg flowed freely today." },
    { topic: "weather", text: "There was no rain today." },
    { topic: "places", text: "The station has a 4.4 Google rating from 1656 ratings." },
    { topic: "review_themes", text: "A small sample of 12 reviews raised staff service in 3 reviews." },
  ],
  facts: { traffic: { as_of_local: "15:30", data_days: 8 }, weather: { today_rain_slots: 0 } },
  sources: {
    traffic: ["traffic.v_traffic (Routes API, demo stand-in for RMI)"],
    weather: ["traffic.weather_slots (Google Weather, core rain_flag)"],
    places: ["traffic.places_details"],
    review_themes: ["traffic.place_review_labels (Gemini labels)"],
  },
};

const card = (topic: AiSummary["sentences"][number]["topic"], data: Parameters<typeof SummaryCard>[0]["data"]) =>
  renderToStaticMarkup(<SummaryCard topic={topic} data={data} timezone="Asia/Jakarta" />);

describe("SummaryCard", () => {
  it("shows a skeleton while the page's summary request is in flight", () => {
    const html = card("traffic", undefined);
    expect(html).toContain('role="status"');
    expect(html).toContain("Loading AI summary");
  });

  it("renders nothing when there is no summary or the request failed", () => {
    expect(card("traffic", null)).toBe("");
    expect(card("traffic", new Error("down"))).toBe("");
    expect(card("traffic", { ...summary, sentences: summary.sentences.filter((s) => s.topic !== "traffic") })).toBe("");
  });

  it("shows only its topic's sentences, with the AI-generated badge, model and times in the site's timezone", () => {
    const html = card("traffic", summary);
    expect(html).toContain("The approach leg had 4 slow slots. The departure leg flowed freely today.");
    expect(html).not.toContain("no rain");
    expect(html).toContain("AI-generated");
    expect(html).toContain("gemini-3.8-flash");
    expect(html).toContain("Data up to 15:30 WIB");
    expect(html).toContain("generated 15:41 WIB");
    expect(html).not.toContain("demo-only");
  });

  it("falls back to the slot when the facts had no traffic slot", () => {
    expect(card("weather", { ...summary, as_of: null })).toContain("Data up to 15:30 WIB");
  });

  it("discloses the topic's facts and source tables", () => {
    const html = card("traffic", summary);
    expect(html).toContain("<summary>Source data</summary>");
    expect(html).toContain("traffic.v_traffic (Routes API, demo stand-in for RMI)");
    expect(html).toContain("&quot;as_of_local&quot;: &quot;15:30&quot;");
    expect(html).not.toContain("today_rain_slots");
  });

  it("notes the small review sample on the review themes card only", () => {
    expect(card("review_themes", summary)).toContain("small sample of Google reviews");
    expect(card("places", summary)).not.toContain("small sample of Google reviews");
  });

  it("formats clock times in the given zone, UTC when unknown", () => {
    expect(clockTime("2026-10-14T08:30:00Z", "Asia/Makassar")).toBe("16:30");
    expect(clockTime("2026-10-14T08:30:00Z", null)).toBe("08:30");
  });
});
