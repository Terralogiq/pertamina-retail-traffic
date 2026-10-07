import { WeatherLatest } from "./api";
import { DemoBadge } from "./DemoBadge";

/** Side-list weather: core temperature_c (no badge) and, when the demo source gave one, its icon with the badge. */
export function SiteWeather({ now }: { now: WeatherLatest | undefined }) {
  if (!now) return null;
  return (
    <div style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 4 }}>
      {now.demo_icon_uri && <img src={`${now.demo_icon_uri}.svg`} alt={now.demo_condition_text ?? ""} width={20} height={20} />}
      <span>{now.temperature_c == null ? "n/a" : `${now.temperature_c.toFixed(1)} °C`}</span>
      {now.demo_icon_uri && <DemoBadge />}
    </div>
  );
}
