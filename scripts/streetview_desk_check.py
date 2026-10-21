#!/usr/bin/env python3
"""Desk check of the approach legs (queue-risk validation step 1).

Pulls Street View Static images, satellite tiles and a transit Nearby Search
along each site's approach leg, so a reviewer can look for a signal, U-turn
gap, bus or angkot stop, merge or crossing just before the Front point.

Leg geometry comes from BigQuery (gcp-coe-sandbox.traffic.routes, active
rows, read-only). Images and raw responses go to --out, never into the repo.

Outputs under --out:
  <site_id>/<leg>_sv_<metres>.jpg      Street View, heading = travel direction
  <site_id>/sat_<metres>.png           satellite z19, centred <metres> before Front
  <site_id>/overview.png               hybrid z17, whole approach leg
  <site_id>/transit_nearby.json        Places Nearby (New), 200 m around Front
  manifest.json                        per-image pano id, capture date, offsets
  calls.json                           request counts by API

Satellite markers: label k sits k * 50 m before the Front point (0 = Front).

Usage: python3 scripts/streetview_desk_check.py --out DIR [--sites 54.801.17,...]
       [--departure 54.801.17,61.761.03] [--reuse]
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segments_lib import (bearing_along, haversine_m, nearest_on_path, path_length_m,  # noqa: E402
                          pin_on_left, walk)

SITES = ["54.801.17", "61.761.03", "74.902.22", "34.121.03", "54.601.80"]
SV_META_URL = "https://maps.googleapis.com/maps/api/streetview/metadata"
SV_URL = "https://maps.googleapis.com/maps/api/streetview"
STATIC_URL = "https://maps.googleapis.com/maps/api/staticmap"
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Metres before the Front point. Dense over the last 200 m, sparse further back.
APPROACH_SV_M = [480, 400, 320, 250, 200, 160, 120, 80, 40, 10]
DEPARTURE_SV_M = [20, 80, 150, 250]       # metres after the Front point
SAT_CENTRES_M = [80, 250, 420]
TRANSIT_TYPES = ["bus_stop", "bus_station", "transit_station", "transit_depot", "taxi_stand"]
NEARBY_FIELDS = "places.id,places.displayName,places.location,places.primaryType,places.types"

CALLS = {"sv_metadata": 0, "sv_image": 0, "static_map": 0, "places_nearby": 0, "errors": 0}


def get_api_key():
    key = os.environ.get("MAPS_API_KEY")
    if key:
        return key.strip()
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         "--secret=MAPS_API_KEY", "--project=gcp-coe-sandbox",
         "--billing-project=gcp-coe-sandbox"],
        capture_output=True, text=True, check=True)
    return out.stdout.strip()


def load_legs(sites):
    """{(site_id, leg): [(lat, lng), ...]} from the active routes rows."""
    ids = ",".join(f"'{s}'" for s in sites)
    sql = ("SELECT site_id, leg, ST_ASGEOJSON(expected_polyline) AS g FROM traffic.routes "
           f"WHERE active AND site_id IN ({ids})")
    out = subprocess.run(
        ["bq", "query", "--project_id=gcp-coe-sandbox", "--use_legacy_sql=false",
         "--format=json", "--max_rows=100", sql],
        capture_output=True, text=True, check=True)
    legs = {}
    for row in json.loads(out.stdout):
        coords = json.loads(row["g"])["coordinates"]
        legs[(row["site_id"], row["leg"])] = [(lat, lng) for lng, lat in coords]
    return legs


def get(url, params, key, kind):
    """GET with the key as a query param (Maps web services). Returns bytes or None."""
    q = urllib.parse.urlencode({**params, "key": key})
    for attempt in range(4):
        CALLS[kind] += 1
        try:
            with urllib.request.urlopen(f"{url}?{q}", timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            CALLS["errors"] += 1
            print(f"  {kind} HTTP {e.code}: {e.read()[:200].decode(errors='replace')}", file=sys.stderr)
            return None
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    CALLS["errors"] += 1
    return None


def nearby(front, key):
    body = {"includedTypes": TRANSIT_TYPES, "maxResultCount": 20,
            "locationRestriction": {"circle": {"center": {"latitude": front[0], "longitude": front[1]},
                                               "radius": 200.0}}}
    req = urllib.request.Request(
        NEARBY_URL, data=json.dumps(body).encode(), method="POST",
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": NEARBY_FIELDS,
                 "Content-Type": "application/json"})
    CALLS["places_nearby"] += 1
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        CALLS["errors"] += 1
        return {"error": e.read().decode(errors="replace")[:500]}


def ll(p):
    return f"{p[0]:.6f},{p[1]:.6f}"


def age_months(date_str, today):
    y, m = (int(x) for x in date_str.split("-")[:2])
    return (today.year - y) * 12 + today.month - m


def street_view(site, leg, pts, marks, out_dir, key, reuse, today, before_front):
    total = path_length_m(pts)
    rows = []
    for m in marks:
        chain = max(0.0, total - m) if before_front else min(total, m)
        p = walk(pts, chain)
        heading = bearing_along(pts, chain, span_m=20.0)
        meta_raw = get(SV_META_URL, {"location": ll(p), "radius": 30, "source": "outdoor"}, key,
                       "sv_metadata")
        meta = json.loads(meta_raw) if meta_raw else {"status": "ERROR"}
        row = {"site_id": site, "leg": leg, "metres": m,
               "metres_ref": "before Front" if before_front else "after Front",
               "requested": ll(p), "heading": round(heading), "status": meta.get("status")}
        if meta.get("error_message"):
            row["error_message"] = meta["error_message"]
        if meta.get("status") == "OK":
            loc = meta["location"]
            row.update(pano_id=meta["pano_id"], date=meta.get("date"),
                       age_months=age_months(meta["date"], today) if meta.get("date") else None,
                       pano_offset_m=round(haversine_m(p, (loc["lat"], loc["lng"]))),
                       copyright=meta.get("copyright"))
            path = os.path.join(out_dir, site, f"{leg}_sv_{m:03d}.jpg")
            row["image"] = path
            if not (reuse and os.path.exists(path)):
                img = get(SV_URL, {"size": "640x400", "pano": meta["pano_id"], "heading": row["heading"],
                                   "fov": 90, "pitch": -5}, key, "sv_image")
                if img:
                    with open(path, "wb") as f:
                        f.write(img)
        rows.append(row)
        print(f"  {site} {leg} {m:3d} m: {row['status']} {row.get('date', '')} "
              f"offset {row.get('pano_offset_m', '-')} m")
    return rows


def static_maps(site, pts, out_dir, key, reuse):
    total = path_length_m(pts)
    markers = [f"size:mid|color:{'red' if k == 0 else 'yellow'}|label:{k}|{ll(walk(pts, total - 50 * k))}"
               for k in range(int(total // 50) + 1)]
    path = "color:0x00ffff80|weight:2|" + "|".join(ll(p) for p in pts)
    jobs = [(f"sat_{c:03d}.png", {"center": ll(walk(pts, total - c)), "zoom": 19, "maptype": "satellite"})
            for c in SAT_CENTRES_M]
    jobs.append(("overview.png", {"center": ll(walk(pts, total / 2)), "zoom": 17, "maptype": "hybrid"}))
    for name, params in jobs:
        dest = os.path.join(out_dir, site, name)
        if reuse and os.path.exists(dest):
            continue
        q = {**params, "size": "640x640", "scale": 2, "path": path}
        body = None
        # One `markers=` param per marker, so each keeps its own label.
        qs = urllib.parse.urlencode([*q.items(), *[("markers", mk) for mk in markers], ("key", key)])
        CALLS["static_map"] += 1
        try:
            with urllib.request.urlopen(f"{STATIC_URL}?{qs}", timeout=60) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            CALLS["errors"] += 1
            print(f"  static_map HTTP {e.code}", file=sys.stderr)
        if body:
            with open(dest, "wb") as f:
                f.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--sites", default=",".join(SITES))
    ap.add_argument("--departure", default="54.801.17,61.761.03",
                    help="sites whose departure leg also gets Street View")
    ap.add_argument("--reuse", action="store_true", help="skip images already on disk")
    a = ap.parse_args()
    sites = a.sites.split(",")
    dep_sites = [s for s in a.departure.split(",") if s]
    key = get_api_key()
    legs = load_legs(sorted(set(sites) | set(dep_sites)))
    today = datetime.date.today()
    manifest = []
    for site in sites:
        os.makedirs(os.path.join(a.out, site), exist_ok=True)
        pts = legs[(site, "approach")]
        print(f"{site}: approach {path_length_m(pts):.0f} m, Front {ll(pts[-1])}")
        manifest += street_view(site, "approach", pts, APPROACH_SV_M, a.out, key, a.reuse, today, True)
        static_maps(site, pts, a.out, key, a.reuse)
        tpath = os.path.join(a.out, site, "transit_nearby.json")
        if not (a.reuse and os.path.exists(tpath)):
            res = nearby(pts[-1], key)
            # Place each stop along approach + departure: negative = before Front.
            both = pts + legs[(site, "departure")][1:]
            for pl in res.get("places", []):
                loc = (pl["location"]["latitude"], pl["location"]["longitude"])
                chain, off, on = nearest_on_path(both, loc)
                pl["metres_from_front"] = round(haversine_m(pts[-1], loc))
                pl["metres_along_from_front"] = round(chain - path_length_m(pts))
                pl["offset_from_leg_m"] = round(off)
                pl["side"] = "left (SPBU side)" if pin_on_left(on, bearing_along(both, chain), loc) else "right"
            with open(tpath, "w") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
    for site in dep_sites:
        pts = legs[(site, "departure")]
        manifest += street_view(site, "departure", pts, DEPARTURE_SV_M, a.out, key, a.reuse, today, False)
    with open(os.path.join(a.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    with open(os.path.join(a.out, "calls.json"), "w") as f:
        json.dump(CALLS, f, indent=1)
    print(json.dumps(CALLS))


if __name__ == "__main__":
    main()
