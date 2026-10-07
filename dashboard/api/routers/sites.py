"""GET /api/sites and GET /api/config."""
import json
import os

from fastapi import APIRouter

from .. import bq, cache

router = APIRouter()

SITES_SQL = f"""
SELECT
  s.site_id, s.name, s.place_id, s.road_name, s.city, s.timezone,
  ST_Y(s.location) AS lat, ST_X(s.location) AS lng,
  r.selected_route_id, r.display_name, r.side, r.leg, r.leg_index, r.expected_distance_m,
  ST_ASGEOJSON(r.expected_polyline) AS expected_polyline
FROM {bq.table("sites")} AS s
LEFT JOIN {bq.table("routes")} AS r ON r.site_id = s.site_id AND r.active
ORDER BY s.site_id, r.leg_index
"""


def group_sites(rows):
    """Flat site x leg rows -> sites with a `legs` list (a site with no active leg gets an empty list)."""
    sites = {}
    for row in rows:
        site = sites.setdefault(row["site_id"], {
            "site_id": row["site_id"], "name": row["name"], "place_id": row["place_id"],
            "road_name": row["road_name"], "city": row["city"], "timezone": row["timezone"],
            "location": {"lat": row["lat"], "lng": row["lng"]}, "legs": [],
        })
        if row["selected_route_id"] is not None:
            polyline = row["expected_polyline"]
            site["legs"].append({
                "selected_route_id": row["selected_route_id"], "display_name": row["display_name"],
                "side": row["side"], "leg": row["leg"], "leg_index": row["leg_index"],
                "expected_distance_m": row["expected_distance_m"],
                "expected_polyline": json.loads(polyline) if polyline else None,
            })
    return list(sites.values())


@router.get("/sites")
def get_sites():
    return cache.default.get_or_compute("sites", {}, lambda: group_sites(bq.query(SITES_SQL)))


@router.get("/config")
def get_config():
    # A browser key restricted to the Maps JavaScript API and our referrers; served only after login.
    return {"maps_browser_key": os.environ.get("MAPS_BROWSER_KEY", ""), "maps_map_id": os.environ.get("MAPS_MAP_ID") or None}
