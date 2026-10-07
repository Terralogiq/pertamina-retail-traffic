import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MIN_RAIN_SLOTS, RainBars, RainScatter, RainToggle, delayScale, groupBySite, rainEffect } from "./RainView";
import { RainSplit } from "./api";

const row = (site_id: string, leg: string, rain: [number | null, number], dry: [number | null, number]): RainSplit => ({
  site_id,
  leg,
  rain: { mean_delay_s: rain[0], n: rain[1] },
  dry: { mean_delay_s: dry[0], n: dry[1] },
});

describe("rain comparison model", () => {
  it("rainEffect is rain minus dry, null when a side is missing", () => {
    expect(rainEffect(row("a", "approach", [40, 8], [25, 90]))).toBe(15);
    expect(rainEffect(row("a", "approach", [null, 0], [25, 90]))).toBeNull();
  });

  it("orders sites by their largest reliable effect; thin-only sites go last", () => {
    const rows = [
      row("small", "approach", [30, 10], [25, 90]), // +5, reliable
      row("thin", "approach", [200, MIN_RAIN_SLOTS - 1], [20, 90]), // +180 but too few rain slots
      row("big", "departure", [60, 12], [20, 90]), // +40, reliable
      row("big", "approach", [21, 12], [20, 90]),
    ];
    const groups = groupBySite(rows);
    expect(groups.map((g) => g.site_id)).toEqual(["big", "small", "thin"]);
    expect(groups[0].legs.map((l) => l.leg)).toEqual(["approach", "departure"]);
  });

  it("delayScale starts at 0 (or below for negative means) and rounds up to a step of 10", () => {
    expect(delayScale([row("a", "approach", [43, 8], [12, 90])])).toEqual({ min: 0, max: 50 });
    expect(delayScale([row("a", "approach", [-4, 8], [12, 90])])).toEqual({ min: -10, max: 20 });
    expect(delayScale([])).toEqual({ min: 0, max: 10 });
  });
});

describe("rain view widgets", () => {
  const names = { a: "SPBU Pertamina 34.121.03" };
  const cities = { a: "Jakarta Selatan" };

  it("labels each site by city and name, and shows n for every leg", () => {
    const html = renderToStaticMarkup(
      <RainBars data={[row("a", "approach", [40, 8], [20, 90])]} source="core" names={names} cities={cities} />,
    );
    expect(html).toContain("Jakarta Selatan");
    expect(html).toContain("SPBU Pertamina 34.121.03");
    expect(html).toContain("n 8/90");
    expect(html).toContain("+20 s");
  });

  it("flags legs with too few rain slots", () => {
    const html = renderToStaticMarkup(<RainBars data={[row("a", "approach", [90, 2], [20, 90])]} source="core" names={names} />);
    expect(html).toContain("rain-leg thin");
    expect(html).toContain("Only 2 rain slots");
  });

  it("uses human labels, never field names", () => {
    const html =
      renderToStaticMarkup(<RainToggle value="core" onChange={() => {}} />) +
      renderToStaticMarkup(<RainBars data={[]} source="demo" names={names} />);
    expect(html).toContain("Measured rain (&gt; 0.1 mm)");
    expect(html).toContain("Google weather condition");
    expect(html).not.toMatch(/rain_flag|demo_rain_flag|precipitation_mm/);
  });

  it("shows an empty state instead of a chart when no slot had measured rain", () => {
    const html = renderToStaticMarkup(
      <RainScatter points={[{ site_id: "a", leg: "approach", precipitation_mm: 0, congestion_index: 1.1 }]} names={names} />,
    );
    expect(html).toContain("No measured rain in this window yet.");
  });
});
