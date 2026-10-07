"""GET /api/places/{site_id}: the latest stored Places run of one site (details, competitors, POI counts).

Every query on places_* filters fetched_at (the partition column) to the last LOOKBACK_DAYS. The latest run is
the run_id of the places_details row with the greatest fetched_at (a Cloud Run retry can give one run_id two
fetched_at values, so run_id is the run key and fetched_at only bounds the scan); nearby and aggregate rows are
then read by that run_id. Places panels carry no demo badge: nothing here is demo-only.
"""
from datetime import timedelta

from fastapi import APIRouter

from .. import bq, cache
from .traffic import _iso, _require_site

router = APIRouter()

LOOKBACK_DAYS = 35  # weekly job + slack; a site with no run in this window has no Places data
NEARBY_MAX = 20  # maxResultCount of the Nearby Search (places_job.places.NEARBY_MAX)
BRANDS = ("Pertamina", "Shell", "BP", "Vivo", "other")  # places_job.places.brand_of

DETAILS_SQL = f"""
SELECT run_id, fetched_at, display_name, rating, user_rating_count, business_status, open_now,
  weekday_descriptions, reviews
FROM {bq.table("places_details")}
WHERE site_id = @site_id AND fetched_at >= @since
ORDER BY fetched_at DESC
LIMIT 1
"""

# One row per radius x brand x is_self over the whole run (self included), so the cap can be judged on every
# result and the competitor counts can leave the site's own place out. A retry under the same run_id re-fetches
# (MERGE bumps fetched_at) but leaves rows the retry no longer returned at the older fetched_at, so only the
# latest attempt per (site_id, radius_m) counts. The window runs before the aggregation, hence the CTE.
NEARBY_SQL = f"""
WITH latest AS (
  SELECT n.site_id, n.radius_m, n.brand, n.place_id
  FROM {bq.table("places_nearby")} AS n
  WHERE n.site_id = @site_id AND n.fetched_at >= @since AND n.run_id = @run_id
  QUALIFY n.fetched_at = MAX(n.fetched_at) OVER (PARTITION BY n.site_id, n.radius_m)
)
SELECT n.radius_m, IFNULL(n.brand, 'other') AS brand, n.place_id = s.place_id AS is_self, COUNT(*) AS count
FROM latest AS n
JOIN {bq.table("sites")} AS s ON s.site_id = n.site_id
GROUP BY n.radius_m, brand, is_self
"""

AGGREGATE_SQL = f"""
SELECT place_type, radius_m, count
FROM {bq.table("places_aggregate")}
WHERE site_id = @site_id AND fetched_at >= @since AND run_id = @run_id
ORDER BY place_type, radius_m
"""


def _details(row):
    reviews = [
        {"rating": r["rating"], "text": r["text"], "language": r["language"],
         "publish_time": _iso(r["publish_time"]), "author_name": r["author_name"]}
        for r in row["reviews"] or []]
    reviews.sort(key=lambda r: r["publish_time"] or "", reverse=True)  # newest first; ISO UTC sorts as text
    return {
        "display_name": row["display_name"], "rating": row["rating"],
        "user_rating_count": row["user_rating_count"], "business_status": row["business_status"],
        "open_now": row["open_now"], "weekday_descriptions": list(row["weekday_descriptions"] or []),
        "reviews": reviews,
    }


def competitors(rows):
    """Nearby groups -> (per radius x brand counts without the site's own place, per-radius totals).

    `capped` is true when the radius returned NEARBY_MAX results counting the site itself (the API's cap applies
    to all results): the competitor count is then a lower bound, shown as `19*` etc. Every brand is listed for
    each radius present, zeros included.
    """
    counts, results = {}, {}
    for r in rows:
        radius = r["radius_m"]
        results[radius] = results.get(radius, 0) + r["count"]
        if not r["is_self"]:
            counts[radius, r["brand"]] = counts.get((radius, r["brand"]), 0) + r["count"]
    by_brand = [{"radius_m": radius, "brand": brand, "count": counts.get((radius, brand), 0)}
                for radius in sorted(results) for brand in BRANDS]
    totals = [{"radius_m": radius, "total": sum(c for (rad, _), c in counts.items() if rad == radius),
               "capped": results[radius] >= NEARBY_MAX}
              for radius in sorted(results)]
    return by_brand, totals


def _latest(site_id):
    since = cache.utc_now() - timedelta(days=LOOKBACK_DAYS)
    found = bq.query(DETAILS_SQL, {"site_id": site_id, "since": since})
    if not found:
        return {"site_id": site_id, "run_id": None, "fetched_at": None, "details": None,
                "competitors": [], "competitor_totals": [], "poi": []}
    row = found[0]
    params = {"site_id": site_id, "since": since, "run_id": row["run_id"]}
    by_brand, totals = competitors(bq.query(NEARBY_SQL, params))
    poi = [{"place_type": r["place_type"], "radius_m": r["radius_m"], "count": r["count"]}
           for r in bq.query(AGGREGATE_SQL, params)]
    return {"site_id": site_id, "run_id": row["run_id"], "fetched_at": _iso(row["fetched_at"]),
            "details": _details(row), "competitors": by_brand, "competitor_totals": totals, "poi": poi}


@router.get("/places/{site_id}")
def places(site_id: str):
    _require_site(site_id)
    return cache.default.get_or_compute("places", {"site_id": site_id}, lambda: _latest(site_id))
