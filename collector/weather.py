"""Weather: Google Weather API `currentConditions:lookup` at each site's Front point.

Maps one response to a weather_slots row (WeatherNext-compatible core + demo_* + raw).
Pure functions plus one HTTP wrapper (`fetch_site`); no google.cloud import.
"""
import json
from urllib.parse import urlencode

import httpjson
from slots import iso, utc_now

API_URL = "https://weather.googleapis.com/v1/currentConditions:lookup"
SOURCE = "google_weather"
RAIN_THRESHOLD_MM = 0.1

# weatherCondition.type values that mean rain is falling (incl. thunderstorms and rain/snow mix).
# Excluded: clear/cloudy/windy and snow-only, hail-only types. Enum list:
# https://developers.google.com/maps/documentation/weather/reference/rest/v1/WeatherCondition
RAIN_CONDITION_TYPES = frozenset({
    "WIND_AND_RAIN", "LIGHT_RAIN_SHOWERS", "CHANCE_OF_SHOWERS", "SCATTERED_SHOWERS", "RAIN_SHOWERS",
    "HEAVY_RAIN_SHOWERS", "LIGHT_TO_MODERATE_RAIN", "MODERATE_TO_HEAVY_RAIN", "RAIN", "LIGHT_RAIN",
    "HEAVY_RAIN", "RAIN_PERIODICALLY_HEAVY", "RAIN_AND_SNOW",
    "THUNDERSTORM", "THUNDERSHOWER", "LIGHT_THUNDERSTORM_RAIN", "SCATTERED_THUNDERSTORMS",
    "HEAVY_THUNDERSTORM",
})


# --- units: the API is asked for METRIC; these convert if a response says otherwise ---

def _convert(value, unit, factors, default_unit):
    """value in `unit` -> value in the target unit. `factors` maps unit -> multiplier."""
    if value is None:
        return None
    unit = unit or default_unit
    if unit not in factors:
        raise ValueError(f"unexpected unit {unit!r}")
    return float(value) * factors[unit]


def temperature_c(obj):
    """{'degrees': 26.4, 'unit': 'CELSIUS'|'FAHRENHEIT'} -> degrees Celsius."""
    if not obj or obj.get("degrees") is None:
        return None
    deg = float(obj["degrees"])
    unit = obj.get("unit") or "CELSIUS"
    if unit == "CELSIUS":
        return deg
    if unit == "FAHRENHEIT":
        return (deg - 32) * 5 / 9
    raise ValueError(f"unexpected unit {unit!r}")


def speed_kmh(obj):
    """{'value': 2, 'unit': 'KILOMETERS_PER_HOUR'|'MILES_PER_HOUR'} -> km/h."""
    return _convert((obj or {}).get("value"), (obj or {}).get("unit"),
                    {"KILOMETERS_PER_HOUR": 1.0, "MILES_PER_HOUR": 1.609344}, "KILOMETERS_PER_HOUR")


def length_mm(obj):
    """{'quantity': 0, 'unit': 'MILLIMETERS'|'INCHES'} -> mm."""
    return _convert((obj or {}).get("quantity"), (obj or {}).get("unit"),
                    {"MILLIMETERS": 1.0, "INCHES": 25.4}, "MILLIMETERS")


def distance_km(obj):
    """{'distance': 16, 'unit': 'KILOMETERS'|'MILES'} -> km."""
    return _convert((obj or {}).get("distance"), (obj or {}).get("unit"),
                    {"KILOMETERS": 1.0, "MILES": 1.609344}, "KILOMETERS")


def _get(d, *path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _num(v, cast=float):
    return cast(v) if v is not None else None


# --- request / response ---

def lookup_url(lat, lng):
    return API_URL + "?" + urlencode({"location.latitude": f"{lat:.7f}", "location.longitude": f"{lng:.7f}",
                                      "unitsSystem": "METRIC"})


def site_fronts(routes):
    """[(site_id, lat, lng)] - each site's SPBU-side Front point (the approach leg's destination).

    Falls back to any approach leg of the site when it has no spbu_side one.
    """
    best = {}
    for r in routes:
        if r["leg_index"] != 0:
            continue
        preferred = r.get("side") in (None, "", "spbu_side")
        cur = best.get(r["site_id"])
        if cur is None or (preferred and not cur[0]):
            best[r["site_id"]] = (preferred, r["dest_lat"], r["dest_lng"])
    return [(sid, lat, lng) for sid, (_, lat, lng) in sorted(best.items())]


def weather_row(site_id, slot, resp, fetched_at, request):
    """One weather_slots row (JSON-ready dict) from a currentConditions response."""
    precip_mm = length_mm(_get(resp, "precipitation", "qpf"))
    condition = _get(resp, "weatherCondition", "type")
    return {
        "site_id": site_id,
        "slot_time": iso(slot),
        "forecast_init_time": None,
        "temperature_c": temperature_c(resp.get("temperature")),
        "dewpoint_c": temperature_c(resp.get("dewPoint")),
        "relative_humidity": _num(resp.get("relativeHumidity")),
        "precipitation_mm": precip_mm,
        "rain_flag": precip_mm > RAIN_THRESHOLD_MM if precip_mm is not None else None,
        "wind_speed_kmh": speed_kmh(_get(resp, "wind", "speed")),
        "wind_direction_deg": _num(_get(resp, "wind", "direction", "degrees")),
        "msl_pressure_hpa": _num(_get(resp, "airPressure", "meanSeaLevelMillibars")),
        "source": SOURCE,
        "ensemble_stat": None,
        "demo_condition_type": condition,
        "demo_condition_text": _get(resp, "weatherCondition", "description", "text"),
        "demo_rain_flag": condition in RAIN_CONDITION_TYPES if condition is not None else None,
        "demo_icon_uri": _get(resp, "weatherCondition", "iconBaseUri"),
        "demo_precip_probability": _num(_get(resp, "precipitation", "probability", "percent")),
        "demo_thunderstorm_prob": _num(resp.get("thunderstormProbability")),
        "demo_feels_like_c": temperature_c(resp.get("feelsLikeTemperature")),
        "demo_uv_index": _num(resp.get("uvIndex"), int),
        "demo_visibility_km": distance_km(resp.get("visibility")),
        "demo_cloud_cover": _num(resp.get("cloudCover"), int),
        "demo_is_daytime": resp.get("isDaytime"),
        "raw": json.dumps({"request": request, "response": resp}, ensure_ascii=False, separators=(",", ":")),
        "fetched_at": iso(fetched_at),
    }


def failed_row(site_id, slot, error, fetched_at, request):
    """A weather_slots row for a failed lookup: every value null, the reason in raw."""
    row = weather_row(site_id, slot, {}, fetched_at, request)
    row["raw"] = json.dumps({"request": request, "error": error}, ensure_ascii=False, separators=(",", ":"))
    return row


def fetch_site(key, site_id, lat, lng, slot):
    """Look up current conditions at (lat, lng). Returns (row, error); error is None on success. Never raises."""
    request = {"latitude": lat, "longitude": lng, "unitsSystem": "METRIC"}
    try:
        resp, error = httpjson.request_json("GET", lookup_url(lat, lng), {"X-Goog-Api-Key": key}, secret=key)
        fetched_at = utc_now()
        if error is None and not resp:
            error = "empty response"
        if error:
            return failed_row(site_id, slot, error, fetched_at, request), error
        return weather_row(site_id, slot, resp, fetched_at, request), None
    except Exception as e:  # noqa: BLE001 - one bad lookup must not drop the slot
        error = f"{type(e).__name__}: {str(e).replace(key, '***')}"
        return failed_row(site_id, slot, error, utc_now(), request), error
