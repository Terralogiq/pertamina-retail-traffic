"""GET /api/traffic/latest, /series, /pattern, /typical-day and /queue-risk. Core columns only (no static_ratio, no demo_*).

v_traffic has no site_id or leg, so every query joins routes (active legs). Every query filters slot_time
(the partition column) and a range is at most bq.MAX_DAYS wide.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from .. import bq, cache, queue_risk
from ..busy import GATE_S, PROVISIONAL_KMH, counts_are_busy, peak_windows, slow_count_sql
from ..holidays import sql_date_list
from .sites import get_sites

router = APIRouter()

PATTERN_MAX_DAYS = 28
# A typical-day hour with fewer readings than this is faded; the profile is ready after this many local dates.
FADED_BELOW = 4
READY_DAYS = 7

# Same columns, in the same order, for latest and series.
_COLUMNS = """
  r.selected_route_id, r.site_id, r.leg, t.slot_time,
  t.duration_in_seconds AS duration_s, t.delay_s, t.congestion_index, t.speed_kmh, t.baseline_samples"""

LATEST_SQL = f"""
SELECT {_COLUMNS}
FROM {bq.table("v_traffic")} AS t
JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
WHERE t.slot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)
QUALIFY ROW_NUMBER() OVER (PARTITION BY t.selected_route_id ORDER BY t.slot_time DESC) = 1
ORDER BY r.site_id, r.leg
"""

SERIES_SQL = f"""
SELECT {_COLUMNS}
FROM {bq.table("v_traffic")} AS t
JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND r.site_id = @site_id
ORDER BY t.slot_time, r.leg
"""

# Day of week 1 = Monday .. 7 = Sunday (BigQuery's DAYOFWEEK is 1 = Sunday) and hour 0-23, both in the site's
# local time. The timezone comes from sites.timezone, never a constant.
PATTERN_SQL = f"""
SELECT
  MOD(EXTRACT(DAYOFWEEK FROM t.slot_time AT TIME ZONE s.timezone) + 5, 7) + 1 AS dow,
  EXTRACT(HOUR FROM t.slot_time AT TIME ZONE s.timezone) AS hour,
  r.leg,
  AVG(t.congestion_index) AS mean_congestion,
  AVG(t.speed_kmh) AS mean_speed_kmh,
  COUNT(*) AS n
FROM {bq.table("v_traffic")} AS t
JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
JOIN {bq.table("sites")} AS s ON s.site_id = r.site_id
WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND s.site_id = @site_id
GROUP BY dow, hour, r.leg
ORDER BY dow, hour, r.leg
"""

# Local hour in the site timezone. Weekend is Saturday, Sunday (BigQuery DAYOFWEEK 7 and 1) or a national
# holiday. Cuti bersama is absent from the date list, so those Mondays stay weekdays.
_WEEKEND = f"""EXTRACT(DAYOFWEEK FROM t.slot_time AT TIME ZONE s.timezone) IN (1, 7)
        OR DATE(t.slot_time, s.timezone) IN ({sql_date_list()})"""

TYPICAL_SQL = f"""
SELECT
  leg,
  day_kind,
  hour,
  quantiles[OFFSET(25)] AS p25_delay_s,
  quantiles[OFFSET(50)] AS median_delay_s,
  quantiles[OFFSET(75)] AS p75_delay_s,
  n,
  slow_n
FROM (
  SELECT
    r.leg AS leg,
    CASE WHEN {_WEEKEND} THEN 'weekend' ELSE 'weekday' END AS day_kind,
    EXTRACT(HOUR FROM t.slot_time AT TIME ZONE s.timezone) AS hour,
    APPROX_QUANTILES(t.delay_s, 100) AS quantiles,
    COUNT(*) AS n,
    COUNTIF({slow_count_sql()}) AS slow_n
  FROM {bq.table("v_traffic")} AS t
  JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
  JOIN {bq.table("sites")} AS s ON s.site_id = r.site_id
  WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND r.site_id = @site_id
    AND t.delay_s IS NOT NULL
  GROUP BY 1, 2, 3
)
ORDER BY leg, day_kind, hour
"""

TYPICAL_DAYS_SQL = f"""
SELECT COUNT(DISTINCT DATE(t.slot_time, s.timezone)) AS days
FROM {bq.table("v_traffic")} AS t
JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
JOIN {bq.table("sites")} AS s ON s.site_id = r.site_id
WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND r.site_id = @site_id
  AND t.delay_s IS NOT NULL
"""


# slow_count_sql() takes one road class through @gate_s and @provisional_kmh. This query spans all sites, so each
# parameter becomes the site's own value. Toll test as in sites.road_class().
_IS_TOLL = "LOWER(s.road_type) LIKE '%toll%'"
_SITE_SLOW = (slow_count_sql()
              .replace("@gate_s", f"IF({_IS_TOLL}, @toll_gate_s, @urban_gate_s)")
              .replace("@provisional_kmh", f"IF({_IS_TOLL}, @toll_provisional_kmh, @urban_provisional_kmh)"))

# Queue-risk proxy (docs/plans/queue-risk.md, "Reproduce"), all sites in one job. A slot is approach-led (ALS)
# when the approach reading is slow and the departure reading of the same slot is not. A full local date has at
# least 40 slots; it recurs when 4 of them (2 h) are ALS.
QUEUE_RISK_SQL = f"""
WITH legs AS (
  SELECT
    r.site_id, r.leg, t.slot_time, t.delay_s,
    DATE(t.slot_time, s.timezone) AS local_date,
    IFNULL(({_SITE_SLOW}), FALSE) AS slow
  FROM {bq.table("v_traffic")} AS t
  JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
  JOIN {bq.table("sites")} AS s ON s.site_id = r.site_id
  WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND t.delay_s IS NOT NULL
),
paired AS (  -- one row per site and slot: both legs come from the same computeRoutes call
  SELECT a.site_id, a.slot_time, a.local_date, a.delay_s AS app_delay_s,
    a.slow AS app_slow, d.slow AS dep_slow, a.slow AND NOT d.slow AS als
  FROM legs AS a
  JOIN legs AS d ON d.site_id = a.site_id AND d.slot_time = a.slot_time AND d.leg = 'departure'
  WHERE a.leg = 'approach'
),
daily AS (
  SELECT site_id, COUNTIF(n >= 40 AND als_n >= 4) AS days_with_2h_als, COUNTIF(n >= 40) AS full_days
  FROM (SELECT site_id, local_date, COUNT(*) AS n, COUNTIF(als) AS als_n FROM paired GROUP BY 1, 2)
  GROUP BY site_id
)
SELECT
  p.site_id,
  ROUND(100 * AVG(IF(p.als, 1, 0)), 1) AS als_pct,
  ROUND(100 * AVG(IF(p.app_slow AND p.dep_slow, 1, 0)), 1) AS both_slow_pct,
  ROUND(100 * AVG(IF(p.dep_slow AND NOT p.app_slow, 1, 0)), 1) AS departure_only_pct,
  APPROX_QUANTILES(IF(p.als, p.app_delay_s, NULL), 100)[OFFSET(50)] AS als_median_delay_s,
  ANY_VALUE(d.days_with_2h_als) AS days_with_2h_als,
  ANY_VALUE(d.full_days) AS full_days
FROM paired AS p
LEFT JOIN daily AS d USING (site_id)
GROUP BY p.site_id
"""


def _iso(value):
    """ISO 8601 UTC string with a Z suffix."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _point(row):
    return {
        "selected_route_id": row["selected_route_id"], "site_id": row["site_id"], "leg": row["leg"],
        "slot_time": _iso(row["slot_time"]), "duration_s": row["duration_s"], "delay_s": row["delay_s"],
        "congestion_index": row["congestion_index"], "speed_kmh": row["speed_kmh"],
        "baseline_samples": row["baseline_samples"],
    }


def _cell(row):
    return {
        "dow": row["dow"], "hour": row["hour"], "leg": row["leg"],
        "mean_congestion": row["mean_congestion"], "mean_speed_kmh": row["mean_speed_kmh"], "n": row["n"],
    }


def _typical_hour(row, hour):
    if row is None:
        return {
            "hour": hour, "median_delay_s": None, "p25_delay_s": None, "p75_delay_s": None,
            "n": 0, "faded": True, "busy": False,
        }
    n = int(row["n"])
    median = row["median_delay_s"]
    return {
        "hour": hour,
        "median_delay_s": median,
        "p25_delay_s": row["p25_delay_s"],
        "p75_delay_s": row["p75_delay_s"],
        "n": n,
        "faded": n < FADED_BELOW,
        "busy": counts_are_busy(int(row.get("slow_n") or 0), n, median),
    }


def _typical_payload(rows, days):
    """One entry per leg that has any reading, both day kinds, hours 0–23 filled in.

    Peak windows stay empty until 7 distinct local dates, even when some hours are already busy.
    """
    ready = int(days) >= READY_DAYS
    index = {(row["leg"], row["day_kind"], int(row["hour"])): row for row in rows}
    legs = []
    for leg in sorted({row["leg"] for row in rows}):
        for day_kind in ("weekday", "weekend"):
            hours = [_typical_hour(index.get((leg, day_kind, hour)), hour) for hour in range(24)]
            legs.append({
                "leg": leg,
                "day_kind": day_kind,
                "hours": hours,
                "windows": peak_windows(hours) if ready else [],
            })
    return {"days": int(days), "ready": ready, "legs": legs}


def _queue_risk_site(row, confidence):
    median = row["als_median_delay_s"]
    entry = {
        "site_id": row["site_id"],
        "als_pct": round(float(row["als_pct"]), 1),
        "both_slow_pct": round(float(row["both_slow_pct"]), 1),
        "departure_only_pct": round(float(row["departure_only_pct"]), 1),
        "days_with_2h_als": int(row["days_with_2h_als"] or 0),
        "full_days": int(row["full_days"] or 0),
        "als_median_delay_s": None if median is None else round(float(median), 1),
    }
    return {**entry, "tier": queue_risk.tier(entry), "confidence": confidence.get(row["site_id"])}


def _queue_risk_payload(rows):
    """Sites that have paired readings in the window, in queue-risk order."""
    confidence = queue_risk.load_confidence()
    sites = sorted((_queue_risk_site(row, confidence) for row in rows), key=queue_risk.sort_key)
    return {"window_days": PATTERN_MAX_DAYS, "sites": sites}


def _parse_time(name, value):
    """ISO 8601 -> aware UTC datetime; naive input counts as UTC. 400 when unparseable."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"{name}: not an ISO 8601 timestamp") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_site(site_id):
    # Shares the /api/sites cache entry, so a known site costs no extra BigQuery job.
    if site_id not in {s["site_id"] for s in get_sites()}:
        raise HTTPException(404, f"unknown site_id {site_id!r}")


@router.get("/traffic/latest")
def traffic_latest():
    return cache.default.get_or_compute(
        "traffic/latest", {}, lambda: [_point(r) for r in bq.query(LATEST_SQL)])


@router.get("/traffic/series")
def traffic_series(site_id: str, from_: str | None = Query(None, alias="from"), to: str | None = None):
    """Per slot per leg. Defaults: `to` = now, `from` = `to` - 24 h. At most 31 days."""
    _require_site(site_id)
    end = _parse_time("to", to) if to else cache.utc_now()
    start = _parse_time("from", from_) if from_ else end - timedelta(hours=24)
    if start >= end:
        raise HTTPException(400, "from must be before to")
    if end - start > timedelta(days=bq.MAX_DAYS):
        raise HTTPException(400, f"range is capped at {bq.MAX_DAYS} days")
    params = {"site_id": site_id, "from_ts": start, "to_ts": end}
    # Keyed on the raw arguments: a default window moves every request, but the entry dies at the next slot.
    return cache.default.get_or_compute(
        "traffic/series", {"site_id": site_id, "from": from_, "to": to},
        lambda: [_point(r) for r in bq.query(SERIES_SQL, params)])


@router.get("/traffic/pattern")
def traffic_pattern(site_id: str, days: int = PATTERN_MAX_DAYS):
    """Day of week (1 = Monday) x local hour -> mean congestion and speed, per leg."""
    if not 1 <= days <= PATTERN_MAX_DAYS:
        raise HTTPException(400, f"days must be between 1 and {PATTERN_MAX_DAYS}")
    _require_site(site_id)
    end = cache.utc_now()
    params = {"site_id": site_id, "from_ts": end - timedelta(days=days), "to_ts": end}
    return cache.default.get_or_compute(
        "traffic/pattern", {"site_id": site_id, "days": days},
        lambda: [_cell(r) for r in bq.query(PATTERN_SQL, params)])


@router.get("/traffic/typical-day")
def traffic_typical_day(site_id: str):
    """Median delay by local hour, weekday and weekend apart, over the last 28 days."""
    _require_site(site_id)
    end = cache.utc_now()
    params = {"site_id": site_id, "from_ts": end - timedelta(days=PATTERN_MAX_DAYS), "to_ts": end}

    def compute():
        site = next(s for s in get_sites() if s["site_id"] == site_id)
        road = site.get("road_class") or "urban"
        band = {**params, "gate_s": GATE_S[road], "provisional_kmh": PROVISIONAL_KMH[road]}
        hour_rows, day_rows = bq.query_all((TYPICAL_SQL, band), (TYPICAL_DAYS_SQL, params))
        days = day_rows[0]["days"] if day_rows else 0
        return _typical_payload(hour_rows, days)

    return cache.default.get_or_compute("traffic/typical-day", {"site_id": site_id}, compute)


@router.get("/traffic/queue-risk")
def traffic_queue_risk():
    """Per site: how often the road is slower before the station than after it, over the last 28 days.

    Not a queue measurement: the tier ranks a road signal and `confidence` is a reviewed judgement.
    """
    end = cache.utc_now()
    params = {
        "from_ts": end - timedelta(days=PATTERN_MAX_DAYS), "to_ts": end,
        "urban_gate_s": GATE_S["urban"], "toll_gate_s": GATE_S["toll"],
        "urban_provisional_kmh": PROVISIONAL_KMH["urban"], "toll_provisional_kmh": PROVISIONAL_KMH["toll"],
    }
    return cache.default.get_or_compute(
        "traffic/queue-risk", {}, lambda: _queue_risk_payload(bq.query(QUEUE_RISK_SQL, params)))
