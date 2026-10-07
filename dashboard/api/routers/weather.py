"""GET /api/weather/latest, /api/weather/series and /api/rain.

Core columns (`temperature_c`, `precipitation_mm`, `rain_flag`, ...) and `demo_*` columns are kept apart in the
responses so the UI can badge the demo-only widgets. Every query filters slot_time; ranges are capped at
bq.MAX_DAYS. Bad parameters give 400.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from .. import bq, cache

router = APIRouter()

LATEST_WINDOW = timedelta(hours=2)
DEFAULT_SERIES_WINDOW = timedelta(hours=24)
MAX_RAIN_DAYS = 28

CORE_FIELDS = "site_id, slot_time, temperature_c, relative_humidity, precipitation_mm, rain_flag, wind_speed_kmh"

LATEST_SQL = f"""
SELECT {CORE_FIELDS},
  demo_condition_type, demo_condition_text, demo_icon_uri, demo_rain_flag, demo_precip_probability
FROM {bq.table("weather_slots")}
WHERE slot_time >= @start
QUALIFY ROW_NUMBER() OVER (PARTITION BY site_id ORDER BY slot_time DESC) = 1
ORDER BY site_id
"""

SERIES_SQL = f"""
SELECT {CORE_FIELDS}, demo_rain_flag, demo_precip_probability
FROM {bq.table("weather_slots")}
WHERE site_id = @site_id AND slot_time >= @start AND slot_time < @end
ORDER BY slot_time
"""

# Traffic legs joined to the weather of their site in the same slot. Slots without a weather row drop out.
_JOIN = f"""
FROM {bq.table("v_traffic")} AS v
JOIN {bq.table("routes")} AS r ON r.selected_route_id = v.selected_route_id
JOIN {bq.table("weather_slots")} AS w ON w.site_id = r.site_id AND w.slot_time = v.slot_time
WHERE v.slot_time >= @start AND w.slot_time >= @start"""
_SITE_FILTER = " AND r.site_id = @site_id"

# Means are over slots with a delay (null while a leg has no baseline); a null flag falls in neither group.
RAIN_SQL = f"""
SELECT
  r.site_id, r.leg,
  AVG(IF(w.rain_flag, v.delay_s, NULL)) AS rain_mean_delay_s,
  COUNTIF(w.rain_flag AND v.delay_s IS NOT NULL) AS rain_n,
  AVG(IF(NOT w.rain_flag, v.delay_s, NULL)) AS dry_mean_delay_s,
  COUNTIF(NOT w.rain_flag AND v.delay_s IS NOT NULL) AS dry_n,
  AVG(IF(w.demo_rain_flag, v.delay_s, NULL)) AS demo_rain_mean_delay_s,
  COUNTIF(w.demo_rain_flag AND v.delay_s IS NOT NULL) AS demo_rain_n,
  AVG(IF(NOT w.demo_rain_flag, v.delay_s, NULL)) AS demo_dry_mean_delay_s,
  COUNTIF(NOT w.demo_rain_flag AND v.delay_s IS NOT NULL) AS demo_dry_n
{_JOIN}{{site_filter}}
GROUP BY r.site_id, r.leg
ORDER BY r.site_id, r.leg
"""

SCATTER_SQL = f"""
SELECT r.site_id, r.leg, w.precipitation_mm, v.congestion_index
{_JOIN}{{site_filter}}
  AND w.precipitation_mm IS NOT NULL AND v.congestion_index IS NOT NULL
ORDER BY r.site_id, r.leg, v.slot_time
"""


def utc_now():
    return datetime.now(timezone.utc)


def _timestamp(name, value):
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"{name}: not an ISO 8601 timestamp") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def series_range(start, end, now):
    """Optional from/to -> (start, end): the last 24 h by default, at most bq.MAX_DAYS wide."""
    end = _timestamp("to", end) if end else now
    start = _timestamp("from", start) if start else end - DEFAULT_SERIES_WINDOW
    if start >= end:
        raise HTTPException(400, "from must be before to")
    if end - start > timedelta(days=bq.MAX_DAYS):
        raise HTTPException(400, f"range is capped at {bq.MAX_DAYS} days")
    return start, end


def _days(value):
    try:
        days = int(value)
    except ValueError:
        raise HTTPException(400, "days: not an integer") from None
    if not 1 <= days <= MAX_RAIN_DAYS:
        raise HTTPException(400, f"days must be 1..{MAX_RAIN_DAYS}")
    return days


def _split(row, prefix=""):
    return {"site_id": row["site_id"], "leg": row["leg"],
            "rain": {"mean_delay_s": row[f"{prefix}rain_mean_delay_s"], "n": row[f"{prefix}rain_n"]},
            "dry": {"mean_delay_s": row[f"{prefix}dry_mean_delay_s"], "n": row[f"{prefix}dry_n"]}}


@router.get("/weather/latest")
def weather_latest():
    return cache.default.get_or_compute(
        "weather/latest", {}, lambda: bq.query(LATEST_SQL, {"start": utc_now() - LATEST_WINDOW}))


@router.get("/weather/series")
def weather_series(site_id: str = "", from_: str | None = Query(None, alias="from"), to: str | None = None):
    if not site_id:
        raise HTTPException(400, "site_id is required")
    series_range(from_, to, utc_now())  # validate before touching the cache

    def compute():
        start, end = series_range(from_, to, utc_now())
        return bq.query(SERIES_SQL, {"site_id": site_id, "start": start, "end": end})

    return cache.default.get_or_compute("weather/series", {"site_id": site_id, "from": from_, "to": to}, compute)


@router.get("/rain")
def rain(site_id: str | None = None, days: str = "28"):
    n_days = _days(days)

    def compute():
        params = {"start": utc_now() - timedelta(days=n_days)}
        site_filter = ""
        if site_id:
            params["site_id"] = site_id
            site_filter = _SITE_FILTER
        summary = bq.query(RAIN_SQL.format(site_filter=site_filter), params)
        scatter = bq.query(SCATTER_SQL.format(site_filter=site_filter), params)
        return {
            "site_id": site_id or None, "days": n_days,
            "core": [_split(row) for row in summary],  # rain_flag, no badge
            "demo": [_split(row, "demo_") for row in summary],  # demo_rain_flag, demo-only
            "scatter": scatter,  # precipitation_mm vs congestion_index, both core
        }

    return cache.default.get_or_compute("rain", {"site_id": site_id, "days": n_days}, compute)
