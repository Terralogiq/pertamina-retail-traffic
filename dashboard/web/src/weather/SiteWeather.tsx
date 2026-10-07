import { WeatherLatest } from "./api";
import { DemoBadge, DemoMarker } from "./DemoBadge";
import "./WeatherPanel.css";

/**
 * Side-list weather: core temperature_c (no badge) and, when the demo source gave one, its condition icon.
 * By default the icon carries the badge. Inside a list that shows one <DemoNote /> for the section, pass `marker`
 * to mark the icon with a <DemoMarker /> instead (contract item 5).
 */
export function SiteWeather({ now, marker = false }: { now: WeatherLatest | undefined; marker?: boolean }) {
  if (!now) return null;
  return (
    <span className="site-weather">
      {now.demo_icon_uri && <img src={`${now.demo_icon_uri}.svg`} alt={now.demo_condition_text ?? ""} width={20} height={20} />}
      <span className="num">{now.temperature_c == null ? "n/a" : `${now.temperature_c.toFixed(1)} °C`}</span>
      {now.demo_icon_uri && (marker ? <DemoMarker /> : <DemoBadge />)}
    </span>
  );
}
