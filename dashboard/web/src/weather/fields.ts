// Which fields are demo-only. Source: docs/plans/dashboard.md, Decisions: Labels.
export const DEMO_ONLY_FIELDS = [
  "static_ratio",
  "demo_rerouted",
  "demo_rain_flag",
  "demo_condition_type",
  "demo_condition_text",
  "demo_precip_probability",
  "demo_thunderstorm_prob",
  "demo_feels_like_c",
  "demo_uv_index",
  "demo_visibility_km",
  "demo_cloud_cover",
] as const;

// The demo-only fields each weather widget shows. A widget listed here must render <DemoBadge />;
// a widget with no entry shows core fields only and carries no badge. weather.test.tsx checks both.
// SiteWeather is map/Overview.tsx's SiteWeatherCell (the live demo icon), which marks the icon with a <DemoMarker />
// under the section's <DemoNote /> instead of a badge (contract item 5).
// demo_icon_uri is not on the Labels list (it is demo_condition_* 's icon), so it is checked separately.
export const WIDGET_DEMO_FIELDS = {
  DemoConditions: ["demo_condition_type", "demo_condition_text", "demo_icon_uri", "demo_rain_flag", "demo_precip_probability"],
  SiteWeather: ["demo_icon_uri"],
  PrecipProbabilityChart: ["demo_precip_probability"],
  RainBars_demo: ["demo_rain_flag"],
  RainToggle: ["demo_rain_flag"],
} as const;
