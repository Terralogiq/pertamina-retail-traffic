"""GET /api/places/analysis: does proximity to POIs relate to traffic? (docs/plans/poi-analysis.md)

Per site: three traffic metrics (mean delay per km, peak congestion, weekday busy-hour share) over the trailing
PATTERN_MAX_DAYS, joined to the latest Places Aggregate counts of six POI groups at three radii. Per (group,
radius): Spearman rho with a bootstrap interval, a permutation p and a leave-one-out range (correlation.py).
Core columns only (no demo_*) and Places is core: nothing here carries a demo-only label.

Registered before the places router in main.py: `/places/analysis` must not be read as `/places/{site_id}`.
"""
from datetime import timedelta

from fastapi import APIRouter, HTTPException

from .. import bq, cache, correlation
from ..busy import GATE_S, PROVISIONAL_KMH, counts_are_busy
from .places import LOOKBACK_DAYS
from .sites import get_sites
from .traffic import _SITE_SLOW, _WEEKEND, PATTERN_MAX_DAYS, READY_DAYS, _iso

router = APIRouter()

# Fixed order: the plot does not sort by rho, so it does not advertise the best of the list. The first group is
# the competitor count: the aggregate counts the site itself, so one is taken off.
GROUPS = (
    ("gas_station", "Other fuel stations"), ("restaurant", "Restaurants"), ("shopping_mall", "Shopping malls"),
    ("lodging", "Lodging"), ("school", "Schools"), ("hospital", "Hospitals"),
)
RADII = (500, 1000, 3000)
METRICS = ("delay", "peak", "busy")
LEGS = ("both", "approach", "departure")
_TYPES = ", ".join(f"'{t}'" for t, _ in GROUPS)

# One row per active leg. Delay is clamped at 0 as on the dashboard and made per km (KM57A's legs are 1 km, the
# others 500 m); the peak is the 95th percentile of the congestion index: the worst 1 slot in 20.
LEG_SQL = f"""
SELECT
  r.site_id, r.leg, MAX(r.expected_distance_m) AS distance_m,
  AVG(GREATEST(t.delay_s, 0)) AS mean_delay_s,
  APPROX_QUANTILES(t.congestion_index, 100)[SAFE_OFFSET(95)] AS peak_congestion,
  COUNT(DISTINCT DATE(t.slot_time, s.timezone)) AS days,
  MIN(t.slot_time) AS first_slot, MAX(t.slot_time) AS last_slot
FROM {bq.table("v_traffic")} AS t
JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
JOIN {bq.table("sites")} AS s ON s.site_id = r.site_id
WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND t.duration_in_seconds IS NOT NULL
GROUP BY r.site_id, r.leg
"""

# Weekday readings per local hour: the inputs of the busy-hour rule (busy.counts_are_busy).
HOUR_SQL = f"""
SELECT
  r.site_id, r.leg, EXTRACT(HOUR FROM t.slot_time AT TIME ZONE s.timezone) AS hour,
  COUNT(*) AS n,
  COUNTIF({_SITE_SLOW}) AS slow_n,
  APPROX_QUANTILES(t.delay_s, 100)[SAFE_OFFSET(50)] AS median_delay_s
FROM {bq.table("v_traffic")} AS t
JOIN {bq.table("routes")} AS r ON r.selected_route_id = t.selected_route_id AND r.active
JOIN {bq.table("sites")} AS s ON s.site_id = r.site_id
WHERE t.slot_time >= @from_ts AND t.slot_time <= @to_ts AND t.delay_s IS NOT NULL
  AND NOT ({_WEEKEND})
GROUP BY r.site_id, r.leg, hour
"""

# Latest run, as in places.py: the run_id of the greatest fetched_at; fetched_at only bounds the scan.
POI_SQL = f"""
WITH latest AS (
  SELECT run_id FROM {bq.table("places_aggregate")} WHERE fetched_at >= @since
  QUALIFY ROW_NUMBER() OVER (ORDER BY fetched_at DESC) = 1
)
SELECT site_id, place_type, radius_m, count, fetched_at
FROM {bq.table("places_aggregate")}
WHERE fetched_at >= @since AND run_id = (SELECT run_id FROM latest) AND place_type IN ({_TYPES})
"""


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def site_traffic(leg_rows, hour_rows, leg):
    """Metrics of one site for `leg` ("both" = mean of the legs that have data), from that site's query rows.

    Busy-hour share is weekday busy hours / 24 per leg. A leg with no weekday reading has no share.
    """
    legs = [r["leg"] for r in leg_rows if leg in ("both", r["leg"])]
    per_leg, busy_hours = {}, {}
    for row in leg_rows:
        km = (row["distance_m"] or 0) / 1000
        hours = [h for h in hour_rows if h["leg"] == row["leg"]]
        busy = sum(1 for h in hours if counts_are_busy(int(h["slow_n"]), int(h["n"]), h["median_delay_s"]))
        busy_hours[row["leg"]] = busy if hours else None
        per_leg[row["leg"]] = {
            "delay": row["mean_delay_s"] / km if row["mean_delay_s"] is not None and km > 0 else None,
            "peak": row["peak_congestion"],
            "busy": busy / 24 if hours else None,
        }
    metrics = {m: _mean([per_leg[name][m] for name in legs]) for m in METRICS}
    return metrics, busy_hours


def poi_counts(rows):
    """Aggregate rows -> {site_id: {group: [count per radius in RADII, None when missing]}}. A site's own place is
    in its gas_station count, so other fuel stations = count - 1."""
    counts = {}
    for r in rows:
        if r["radius_m"] not in RADII:
            continue
        count = max(r["count"] - 1, 0) if r["place_type"] == "gas_station" else r["count"]
        site = counts.setdefault(r["site_id"], {t: [None] * len(RADII) for t, _ in GROUPS})
        site[r["place_type"]][RADII.index(r["radius_m"])] = count
    return counts


def correlations(sites, metric):
    """One entry per (group, radius). A site joins a test when it has the traffic metric and that POI count."""
    stats = []
    for group, _ in GROUPS:
        for i, radius in enumerate(RADII):
            pairs = [(s["poi"][group][i], s["metrics"][metric]) for s in sites
                     if s["poi"] and s["poi"][group][i] is not None and s["metrics"][metric] is not None]
            stats.append({"group": group, "radius_m": radius,
                          **correlation.analyse([p[0] for p in pairs], [p[1] for p in pairs])})
    return stats


def build_sites(sites, leg_rows, hour_rows, poi_rows, leg, exclude_toll):
    """The per-site table. Sites without traffic or without a Places run keep their row with empty values."""
    poi = poi_counts(poi_rows)
    out = []
    for site in sites:
        if exclude_toll and site["road_class"] == "toll":
            continue
        rows = [r for r in leg_rows if r["site_id"] == site["site_id"]]
        hours = [h for h in hour_rows if h["site_id"] == site["site_id"]]
        metrics, busy_hours = site_traffic(rows, hours, leg)
        out.append({
            "site_id": site["site_id"], "name": site["name"], "city": site["city"],
            "road_class": site["road_class"], "metrics": metrics, "busy_hours": busy_hours,
            "poi": poi.get(site["site_id"]),
        })
    return out


def ready_days(leg_rows):
    """Local dates with a reading at the thinnest site (a site's best leg); 0 without traffic."""
    best = {}
    for r in leg_rows:
        best[r["site_id"]] = max(best.get(r["site_id"], 0), int(r["days"]))
    return min(best.values()) if best else 0


def payload(data, sites, metric, leg, exclude_toll):
    leg_rows, hour_rows, poi_rows = data["legs"], data["hours"], data["poi"]
    days = ready_days(leg_rows)
    ready = days >= READY_DAYS
    rows = build_sites(sites, leg_rows, hour_rows, poi_rows, leg, exclude_toll) if ready else []
    slots = [r[k] for r in leg_rows for k in ("first_slot", "last_slot") if r[k] is not None]
    fetched = [r["fetched_at"] for r in poi_rows]
    return {
        "metric": metric, "leg": leg, "exclude_toll": exclude_toll,
        "ready": ready, "days": days, "ready_days": READY_DAYS,
        "window": {"from": _iso(min(slots)) if slots else None, "to": _iso(max(slots)) if slots else None},
        "places_run": _iso(max(fetched)) if fetched else None,
        "groups": [{"id": g, "label": label} for g, label in GROUPS],
        "radii": list(RADII),
        "sites": rows,
        "stats": correlations(rows, metric) if ready else [],
    }


def _fetch():
    now = cache.utc_now()
    traffic = {
        "from_ts": now - timedelta(days=PATTERN_MAX_DAYS), "to_ts": now,
        "urban_gate_s": GATE_S["urban"], "toll_gate_s": GATE_S["toll"],
        "urban_provisional_kmh": PROVISIONAL_KMH["urban"], "toll_provisional_kmh": PROVISIONAL_KMH["toll"],
    }
    legs, hours, poi = bq.query_all(
        (LEG_SQL, {k: traffic[k] for k in ("from_ts", "to_ts")}), (HOUR_SQL, traffic),
        (POI_SQL, {"since": now - timedelta(days=LOOKBACK_DAYS)}))
    return {"legs": legs, "hours": hours, "poi": poi}


@router.get("/places/analysis")
def places_analysis(metric: str = "delay", leg: str = "both", exclude_toll: bool = False):
    if metric not in METRICS:
        raise HTTPException(400, f"metric must be one of {', '.join(METRICS)}")
    if leg not in LEGS:
        raise HTTPException(400, f"leg must be one of {', '.join(LEGS)}")

    def compute():
        # The BigQuery rows are shared by every metric, leg and toll switch; only the statistics differ.
        data = cache.default.get_or_compute("places/analysis/data", {}, _fetch)
        return payload(data, get_sites(), metric, leg, exclude_toll)

    return cache.default.get_or_compute(
        "places/analysis", {"metric": metric, "leg": leg, "exclude_toll": exclude_toll}, compute)
