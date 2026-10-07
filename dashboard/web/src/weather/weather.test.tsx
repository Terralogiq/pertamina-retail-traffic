import { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEMO_ONLY_FIELDS, WIDGET_DEMO_FIELDS } from "./fields";
import { CoreConditions, DemoConditions, PrecipProbabilityChart, WeatherChart } from "./WeatherPanel";
import { RainBars, RainScatter, RainToggle } from "./RainView";
import { SiteWeather } from "./SiteWeather";
import { WeatherLatest, WeatherSeriesPoint, getRain, getWeatherSeries, RainSplit } from "./api";
import { localTime, zoneLabel } from "./time";

// The visible badge element, not any "demo-only" text (DemoMarker keeps that text for screen readers only).
const BADGE = 'class="demo-badge"';

const now: WeatherLatest = {
  site_id: "34.121.03",
  slot_time: "2026-10-07T03:00:00Z",
  temperature_c: 29.1,
  relative_humidity: 80,
  precipitation_mm: 0.4,
  rain_flag: true,
  wind_speed_kmh: 9,
  demo_condition_type: "LIGHT_RAIN",
  demo_condition_text: "Light rain",
  demo_icon_uri: "https://maps.gstatic.com/weather/v1/rain_light",
  demo_rain_flag: true,
  demo_precip_probability: 60,
};
const series: WeatherSeriesPoint[] = [{ ...now, demo_rain_flag: true, demo_precip_probability: 60 }];
const split: RainSplit[] = [
  { site_id: "34.121.03", leg: "approach", rain: { mean_delay_s: 40, n: 5 }, dry: { mean_delay_s: 20, n: 90 } },
];
const names = { "34.121.03": "SPBU Simatupang" };

// One renderer per entry of WIDGET_DEMO_FIELDS.
const demoWidgets: Record<keyof typeof WIDGET_DEMO_FIELDS, () => ReactElement> = {
  DemoConditions: () => <DemoConditions now={now} />,
  SiteWeather: () => <SiteWeather now={now} />,
  PrecipProbabilityChart: () => <PrecipProbabilityChart series={series} />,
  RainBars_demo: () => <RainBars data={split} source="demo" names={names} />,
  RainToggle: () => <RainToggle value="core" onChange={() => {}} />,
};

const coreWidgets: Record<string, () => ReactElement> = {
  CoreConditions: () => <CoreConditions now={now} tz="Asia/Jakarta" />,
  WeatherChart: () => <WeatherChart series={series} />,
  SiteWeather_core: () => <SiteWeather now={{ ...now, demo_icon_uri: null }} />,
  RainBars_core: () => <RainBars data={split} source="core" names={names} />,
  RainScatter: () => <RainScatter points={[]} names={names} />,
};

afterEach(() => vi.unstubAllGlobals());

describe("demo-only badge", () => {
  it("every widget listed in WIDGET_DEMO_FIELDS renders the badge", () => {
    expect(Object.keys(demoWidgets).sort()).toEqual(Object.keys(WIDGET_DEMO_FIELDS).sort());
    for (const [name, render] of Object.entries(demoWidgets)) {
      expect(renderToStaticMarkup(render()), name).toContain(BADGE);
    }
  });

  it("core widgets carry no badge", () => {
    for (const [name, render] of Object.entries(coreWidgets)) {
      expect(renderToStaticMarkup(render()), name).not.toContain(BADGE);
    }
  });

  it("covers every demo_* field the weather endpoints return", () => {
    const covered = new Set<string>(Object.values(WIDGET_DEMO_FIELDS).flat());
    for (const field of Object.keys(now).filter((k) => k.startsWith("demo_"))) {
      expect(covered.has(field), field).toBe(true);
    }
  });

  it("every widget field is a demo field: on the Labels list, or an icon of demo_condition_*", () => {
    const labelled = new Set<string>([...DEMO_ONLY_FIELDS, "demo_icon_uri"]);
    for (const field of Object.values(WIDGET_DEMO_FIELDS).flat()) expect(labelled.has(field), field).toBe(true);
  });

  it("the demo widget shows the demo fields it declares", () => {
    const html = renderToStaticMarkup(<DemoConditions now={now} />);
    expect(html).toContain("Light rain");
    expect(html).toContain("LIGHT_RAIN");
    expect(html).toContain("rain_light.svg");
    expect(html).toContain("60 %");
  });
});

describe("site list weather", () => {
  it("shows temperature_c, and nothing without a slot", () => {
    expect(renderToStaticMarkup(<SiteWeather now={now} />)).toContain("29.1 °C");
    expect(renderToStaticMarkup(<SiteWeather now={undefined} />)).toBe("");
  });
});

describe("api client", () => {
  it("builds the series and rain URLs", async () => {
    const f = vi.fn().mockImplementation(() => Promise.resolve(Response.json([])));
    vi.stubGlobal("fetch", f);
    await getWeatherSeries("34.121.03", "2026-10-01T00:00:00Z");
    await getRain(7);
    await getRain(28, "34.121.03");
    expect(f.mock.calls.map((c) => c[0])).toEqual([
      "/api/weather/series?site_id=34.121.03&from=2026-10-01T00%3A00%3A00Z",
      "/api/rain?days=7",
      "/api/rain?days=28&site_id=34.121.03",
    ]);
  });
});

describe("site-local time", () => {
  it("labels WIB and WITA and shifts the clock", () => {
    expect(zoneLabel("Asia/Jakarta")).toBe("WIB");
    expect(zoneLabel("Asia/Makassar")).toBe("WITA");
    expect(localTime("2026-10-07T03:00:00Z", "Asia/Jakarta")).toBe("10:00");
    expect(localTime("2026-10-07T03:00:00Z", "Asia/Makassar")).toBe("11:00");
  });
});
