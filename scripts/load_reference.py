#!/usr/bin/env python3
"""Load the reference tables traffic.sites and traffic.routes (MERGE, re-runnable).

  data/sites.csv  + Places Place Details (name, location)  -> traffic.sites
  data/routes.csv (+ decoded expected_polyline)            -> traffic.routes

Rows are staged with `bq load` into traffic._stg_sites / _stg_routes (geometry as
WKT strings), MERGEd into the real tables on the key, and the staging tables are
dropped. Places is called live (Place Details: id, displayName, location); the key
comes from $MAPS_API_KEY or Secret Manager. No Python BigQuery client needed.

Usage: python3 scripts/load_reference.py [--dry-run]
  --dry-run  build and print the rows; no BigQuery writes (still calls Places)
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import places_test_fetch as ptf  # noqa: E402
import segments_lib as lib  # noqa: E402

SITES_CSV = os.path.join(ROOT, "data", "sites.csv")
ROUTES_CSV = os.path.join(ROOT, "data", "routes.csv")
PROJECT = "gcp-coe-sandbox"
LOCATION = "asia-southeast2"
DETAILS_MASK = "id,displayName,location"

SIDE_LABEL = {"spbu_side": "SPBU side", "opposite": "Opposite side"}

SITES_SCHEMA = "site_id:STRING,name:STRING,place_id:STRING,location_wkt:STRING,road_name:STRING,city:STRING,road_type:STRING,timezone:STRING"
ROUTES_SCHEMA = (
    "selected_route_id:STRING,display_name:STRING,origin_wkt:STRING,destination_wkt:STRING,"
    "mid_wkt:STRING,site_id:STRING,side:STRING,leg:STRING,call_id:STRING,leg_index:INTEGER,"
    "expected_wkt:STRING,expected_distance_m:INTEGER,active:BOOLEAN,"
    "demo_origin_heading:INTEGER,demo_dest_heading:INTEGER")

MERGE_SITES = """
MERGE traffic.sites AS t
USING (SELECT * EXCEPT (location_wkt), ST_GEOGFROMTEXT(location_wkt) AS location
       FROM traffic._stg_sites) AS s
ON t.site_id = s.site_id
WHEN MATCHED THEN UPDATE SET
  name = s.name, place_id = s.place_id, location = s.location,
  road_name = s.road_name, city = s.city, road_type = s.road_type, timezone = s.timezone
WHEN NOT MATCHED THEN INSERT (site_id, name, place_id, location, road_name, city, road_type, timezone)
  VALUES (s.site_id, s.name, s.place_id, s.location, s.road_name, s.city, s.road_type, s.timezone)
"""

MERGE_ROUTES = """
MERGE traffic.routes AS t
USING (SELECT
         selected_route_id, display_name,
         ST_GEOGFROMTEXT(origin_wkt) AS origin,
         ST_GEOGFROMTEXT(destination_wkt) AS destination,
         [ST_GEOGFROMTEXT(mid_wkt)] AS intermediates,
         site_id, side, leg, call_id, leg_index,
         ST_GEOGFROMTEXT(expected_wkt) AS expected_polyline,
         expected_distance_m, active, demo_origin_heading, demo_dest_heading
       FROM traffic._stg_routes) AS s
ON t.selected_route_id = s.selected_route_id
WHEN MATCHED THEN UPDATE SET
  display_name = s.display_name, origin = s.origin, destination = s.destination,
  intermediates = s.intermediates, site_id = s.site_id, side = s.side, leg = s.leg,
  call_id = s.call_id, leg_index = s.leg_index, expected_polyline = s.expected_polyline,
  expected_distance_m = s.expected_distance_m, active = s.active,
  demo_origin_heading = s.demo_origin_heading, demo_dest_heading = s.demo_dest_heading
WHEN NOT MATCHED THEN INSERT (
  selected_route_id, display_name, origin, destination, intermediates, site_id, side, leg,
  call_id, leg_index, expected_polyline, expected_distance_m, active, rmi_state,
  demo_origin_heading, demo_dest_heading)
  VALUES (
  s.selected_route_id, s.display_name, s.origin, s.destination, s.intermediates, s.site_id,
  s.side, s.leg, s.call_id, s.leg_index, s.expected_polyline, s.expected_distance_m, s.active,
  NULL, s.demo_origin_heading, s.demo_dest_heading)
"""


# --- pure helpers (no network, no BigQuery) -------------------------------------

def point_wkt(lat, lng):
    return f"POINT({float(lng):.7f} {float(lat):.7f})"


def linestring_wkt(pts):
    """[(lat, lng), ...] -> WKT LINESTRING (x = lng, y = lat)."""
    return "LINESTRING(" + ", ".join(f"{lng:.7f} {lat:.7f}" for lat, lng in pts) + ")"


def mid_point(pts):
    """Point at half the polyline's length, as (lat, lng)."""
    return lib.walk(pts, lib.path_length_m(pts) / 2)


def display_name(site, route):
    """e.g. "SPBU 34.121.03 Jl. TB Simatupang · SPBU side · Approach"."""
    side = SIDE_LABEL.get(route["side"], route["side"])
    return f"SPBU {site['spbu_code']} {site['road']} · {side} · {route['leg'].capitalize()}"


def site_row(site, details):
    """`details` is the Place Details response, or {} when it failed."""
    loc = details.get("location") or {}
    has_loc = "latitude" in loc and "longitude" in loc
    return {
        "site_id": site["spbu_code"],
        "name": (details.get("displayName") or {}).get("text"),
        "place_id": site["place_id"],
        "location_wkt": point_wkt(loc["latitude"], loc["longitude"]) if has_loc else None,
        "road_name": site["road"],
        "city": site["city"],
        "road_type": site["road_type"],
        "timezone": site["timezone"],
    }


def route_row(route, site):
    pts = lib.decode_polyline(route["expected_polyline"])
    if len(pts) < 2:
        raise ValueError(f"{route['selected_route_id']}: expected_polyline has < 2 points")
    return {
        "selected_route_id": route["selected_route_id"],
        "display_name": display_name(site, route),
        "origin_wkt": point_wkt(route["origin_lat"], route["origin_lng"]),
        "destination_wkt": point_wkt(route["dest_lat"], route["dest_lng"]),
        "mid_wkt": point_wkt(*mid_point(pts)),
        "site_id": route["site_id"],
        "side": route["side"],
        "leg": route["leg"],
        "call_id": route["call_id"],
        "leg_index": int(route["leg_index"]),
        "expected_wkt": linestring_wkt(pts),
        "expected_distance_m": int(route["expected_distance_m"]),
        "active": route["status"] == "ok",
        "demo_origin_heading": int(route["origin_heading"]),
        "demo_dest_heading": int(route["dest_heading"]),
    }


def build_route_rows(routes, sites):
    by_code = {s["spbu_code"]: s for s in sites}
    return [route_row(r, by_code[r["site_id"]]) for r in routes]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --- network / BigQuery ----------------------------------------------------------

def fetch_details(place_id, key):
    status, body = ptf.http(
        "GET", ptf.DETAILS_URL.format(place_id), key, mask=DETAILS_MASK,
        params={"languageCode": "id", "regionCode": "ID"})
    if status != 200:
        print(f"  Place Details {place_id}: HTTP {status}: {json.dumps(body)[:300]}", file=sys.stderr)
        return {}
    return body


def bq(*args, stdin=None):
    cmd = ["bq", f"--project_id={PROJECT}", f"--location={LOCATION}", *args]
    return subprocess.run(cmd, input=stdin, text=True, check=True)


def merge(table, schema, rows, sql):
    stg = f"traffic._stg_{table}"
    with tempfile.NamedTemporaryFile("w", suffix=".ndjson", delete=False) as f:
        f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    try:
        bq("load", "--replace", "--source_format=NEWLINE_DELIMITED_JSON", stg, f.name, schema)
        bq("query", "--use_legacy_sql=false", "--quiet", stdin=sql)
    finally:
        os.unlink(f.name)
        bq("rm", "-f", "-t", stg)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sites = read_csv(SITES_CSV)
    routes = read_csv(ROUTES_CSV)
    key = ptf.get_api_key()
    site_rows = [site_row(s, fetch_details(s["place_id"], key)) for s in sites]
    route_rows = build_route_rows(routes, sites)
    missing = [r["site_id"] for r in site_rows if r["location_wkt"] is None]
    if missing:
        sys.exit(f"no Place Details location for sites {missing}; not loading")

    if args.dry_run:
        for r in site_rows + route_rows:
            print(json.dumps(r, ensure_ascii=False)[:300])
        return
    merge("sites", SITES_SCHEMA, site_rows, MERGE_SITES)
    merge("routes", ROUTES_SCHEMA, route_rows, MERGE_ROUTES)
    print(f"merged {len(site_rows)} sites, {len(route_rows)} routes")


if __name__ == "__main__":
    main()
