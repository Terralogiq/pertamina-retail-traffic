#!/usr/bin/env python3
"""Propose Entry / Front / Exit points for every SPBU and validate them.

Per site and side, ONE Routes call runs Entry -> Front (stop) -> Exit and returns
two legs: Approach (Entry -> Front) and Departure (Front -> Exit).

How the points are found:
  * Auto sites: route from the Places location in 8 directions; the first step
    that turns onto the named road (data/sites.csv `road`) marks where the main
    road is. The SPBU-side direction is the one with the station on the left
    (Indonesia drives on the left). The road is then traced along its geometry.
  * Linked sites (data/segment_links.csv): the user's directions link gives the
    start of the road and the direction; the place ID is checked against sites.csv.
    An `exit_url` (SPBU -> Exit link) fixes the Exit instead of measuring it.
  * The Opposite side mirrors the SPBU side (the same road, reverse direction).
  * Each side is validated with one TRAFFIC_AWARE call (segments_lib.validate_leg).
    A side that fails every variant is written with status needs_link.
  * Urban sites are PROBED with routeModifiers.avoidTolls = true so that road tracing does
    not follow a toll road that shares the arterial's alignment (site 3). The validation
    call is the plain collector request (no modifier); a leg that runs on a toll road
    fails it. The toll site (5) is probed without the modifier.

Reads : data/sites.csv, data/segment_links.csv (optional)
Writes: data/routes.csv, out/segments/polylines.json (git-ignored)
Cache : out/segments/cache/ (git-ignored; one file per distinct API request, so a rerun
        is free and deterministic; delete the folder to re-query everything)

Usage: python3 scripts/propose_segments.py
The API key comes from $MAPS_API_KEY or Secret Manager; it is never printed.
"""
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import segments_lib as lib  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES_CSV = os.path.join(ROOT, "data", "sites.csv")
LINKS_CSV = os.path.join(ROOT, "data", "segment_links.csv")
ROUTES_CSV = os.path.join(ROOT, "data", "routes.csv")
OUT_DIR = os.path.join(ROOT, "out", "segments")
CACHE_DIR = os.path.join(OUT_DIR, "cache")
POLYLINES_JSON = os.path.join(OUT_DIR, "polylines.json")

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
PLACES_URL = "https://places.googleapis.com/v1/places/"

PROBE_MASK = (
    "routes.distanceMeters,routes.polyline.encodedPolyline,"
    "routes.legs.startLocation,routes.legs.endLocation,"
    "routes.legs.steps.distanceMeters,routes.legs.steps.navigationInstruction,"
    "routes.legs.steps.startLocation,routes.legs.steps.endLocation,"
    "routes.legs.steps.polyline.encodedPolyline")
TRAFFIC_MASK = (
    "routes.distanceMeters,routes.duration,routes.staticDuration,"
    "routes.legs.distanceMeters,routes.legs.duration,routes.legs.staticDuration,"
    "routes.legs.polyline.encodedPolyline,routes.legs.startLocation,routes.legs.endLocation,"
    "routes.legs.steps.navigationInstruction")
PLACES_MASK = "location,addressComponents"

# Maneuvers a road trace may pass through; anything else means the route left the road.
TRACE_OK = {"", "DEPART", "STRAIGHT", "NAME_CHANGE", "TURN_SLIGHT_LEFT", "TURN_SLIGHT_RIGHT",
            "FORK_LEFT", "FORK_RIGHT", "MERGE"}
# (leg length factor in, out) tried in order; the first that validates wins.
VARIANTS = [(1.0, 1.0), (0.8, 1.0), (1.0, 0.8), (0.8, 0.8)]
SHORT_VARIANTS = [(0.6, 1.0), (1.0, 0.6), (0.6, 0.6)]   # legs down to 300 m (urban)
SHORT_LIMIT_M = 300
# Per-site exceptions: keep the link's Entry as given; optionally a minimum leg length
# (`min_m`) and maneuver labels the user verified are not turns. A fixed Exit comes from the
# link row's `exit_url`, not from here.
# Site 3's "Turn left" label (a lane split; 483 m vs 480 m straight) is from the user's
# SPBU -> Exit link in data/segment_links.csv, checked on the map.
LINK_ENTRY_SITES = {"3": {"accept": {"departure": ("TURN_LEFT",)}}}   # user, 2026-10-06
FRONT_FAR_M = 120          # Front farther than this from the pin is flagged

SIDES = ("spbu_side", "opposite")
# Every site is measured on the SPBU side only (user, 2026-10-06): the opposite
# carriageway isn't the traffic the station sees. The opposite-side derivation is kept
# for reference; add a side back here to re-enable it.


def sides_for(site, toll):
    return SIDES[:1]
ROUTES_COLUMNS = [
    "selected_route_id", "site_no", "site_id", "side", "leg", "call_id", "leg_index",
    "origin_lat", "origin_lng", "origin_heading", "dest_lat", "dest_lng", "dest_heading",
    "expected_distance_m", "expected_polyline", "status", "note"]


class Maps:
    """Routes/Places client with an on-disk response cache and a call counter."""

    def __init__(self, key):
        self.key = key
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.made = {"routes_probe": 0, "routes_traffic": 0, "places": 0}
        self.cached = 0
        self.avoid_tolls = False     # set per site: probes of urban sites avoid toll roads

    def _call(self, kind, method, url, body, mask):
        digest = hashlib.sha256(json.dumps([method, url, body, mask], sort_keys=True).encode())
        path = os.path.join(CACHE_DIR, digest.hexdigest()[:24] + ".json")
        if os.path.exists(path):
            self.cached += 1
            with open(path) as f:
                return json.load(f)["response"]
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json", "X-Goog-Api-Key": self.key,
                   "X-Goog-FieldMask": mask}
        out = {"error": {"message": "retries exhausted"}}
        for attempt in range(4):
            req = urllib.request.Request(url, data, headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    out = json.loads(r.read().decode() or "{}")
                break
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="replace")
                if e.code == 429 or e.code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                out = {"error": {"code": e.code, "message": raw.replace(self.key, "***")[:300]}}
                break
            except (urllib.error.URLError, TimeoutError) as e:
                out = {"error": {"message": str(e).replace(self.key, "***")[:200]}}
                time.sleep(2 ** attempt)
        self.made[kind] += 1
        if "error" not in out:
            with open(path, "w") as f:
                json.dump({"kind": kind, "response": out}, f)
        return out

    def probe(self, origin, dest, **extra):
        """Traffic-unaware route used only to read road geometry and step names."""
        body = {"origin": origin, "destination": dest, "travelMode": "DRIVE", "languageCode": "en"}
        if self.avoid_tolls:
            body["routeModifiers"] = {"avoidTolls": True}
        body.update(extra)
        return self._call("routes_probe", "POST", ROUTES_URL, body, PROBE_MASK)

    def traffic(self, origin, stop, dest):
        """The collector's request (Entry -> Front stop -> Exit, TRAFFIC_AWARE), no modifiers."""
        body = {"origin": origin, "intermediates": [stop], "destination": dest,
                "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE", "languageCode": "en"}
        return self._call("routes_traffic", "POST", ROUTES_URL, body, TRAFFIC_MASK)

    def place(self, place_id):
        return self._call("places", "GET", PLACES_URL + place_id, None, PLACES_MASK)


def get_api_key():
    key = os.environ.get("MAPS_API_KEY")
    if key:
        return key.strip()
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest", "--secret=MAPS_API_KEY",
         "--project=gcp-coe-sandbox", "--billing-project=gcp-coe-sandbox"],
        capture_output=True, text=True, check=True)
    return out.stdout.strip()


def wp(p, heading=None, via=None, place_id=None):
    if place_id:
        w = {"placeId": place_id}
    else:
        w = {"location": {"latLng": {"latitude": p[0], "longitude": p[1]}}}
    if heading is not None:
        w.setdefault("location", {})["heading"] = int(round(heading)) % 360
    if via is not None:
        w["via"] = via
    return w


# --- road geometry from probe routes -------------------------------------------

def _steps(resp):
    routes = resp.get("routes") or []
    if not routes or not routes[0].get("legs"):
        return []
    return routes[0]["legs"][0].get("steps", [])


def _step_info(st):
    ni = st.get("navigationInstruction") or {}
    pts = lib.decode_polyline((st.get("polyline") or {}).get("encodedPolyline", ""))
    return ni.get("maneuver", ""), ni.get("instructions", ""), pts


def clean_stretch(steps):
    """Polyline of the leading steps that stay on the road, and what stopped them."""
    pts, blocked = [], None
    for st in steps:
        m, _, step_pts = _step_info(st)
        if pts and m not in TRACE_OK:
            blocked = m
            break
        pts += step_pts if not pts else step_pts[1:]
    return pts, blocked


def trace(maps, start, heading, need_m, path=None):
    """Follow the road from `start` (heading `heading`) for at least `need_m`.

    Returns (path, blocked): `blocked` is None if `need_m` was reached, else why not.
    Pass an existing `path` to extend it from its end.
    """
    path = list(path or [])
    blocked = None
    for _ in range(8):
        remaining = need_m - lib.path_length_m(path)
        if remaining <= 0:
            return path, None
        cur, h = ((path[-1], lib.bearing_along(path, lib.path_length_m(path))) if path
                  else (start, heading))
        reach, new = min(remaining + 200, 1000), []
        while reach >= 250:       # aim closer if the route leaves the road for a side street
            resp = maps.probe(wp(cur, h), wp(lib.dest_point(cur, h, reach)))
            new, blocked = clean_stretch(_steps(resp))
            if lib.path_length_m(new) >= 20:
                break
            new, reach = [], reach / 2
        if not new:
            return path, blocked or "no progress"
        path += new if not path else new[1:]
    return path, None if lib.path_length_m(path) >= need_m else blocked


def find_road_entry(maps, pin, names):
    """Where the named road is, from routes leaving the Places location.

    Returns {point, bearing, dist_m, instruction} for the step that turns onto
    the road nearest to the pin, or None.
    """
    best = None
    for heading in range(0, 360, 45):
        resp = maps.probe(wp(pin, heading), wp(lib.dest_point(pin, heading, 1200)))
        for st in _steps(resp):
            m, text, pts = _step_info(st)
            road = lib.road_of_instruction(text)
            if len(pts) < 2 or not road or not any(lib.road_matches(n, road) for n in names):
                continue
            d = lib.haversine_m(pts[0], pin)
            # Prefer turns onto the road (a junction) over a DEPART from the pin itself.
            rank = (d + (25 if m == "DEPART" else 0), d)
            if best is None or rank < best[0]:
                best = (rank, {"point": pts[0], "bearing": lib.bearing_along(pts, 0, 30),
                               "dist_m": d, "instruction": text.splitlines()[0]})
            break
    return best[1] if best else None


def link_anchor(maps, link_url, site):
    """(entry point, heading, place_id) from a directions link, place ID checked."""
    entry, place_id = lib.parse_directions_url(link_url)
    if place_id != site["place_id"]:
        raise ValueError(f"site {site['site_no']}: link place {place_id} != sites.csv {site['place_id']}")
    resp = maps.probe(wp(entry), wp(None, place_id=place_id))
    steps = _steps(resp)
    pts = [p for st in steps[:3] for p in _step_info(st)[2]]
    if len(pts) < 2:
        raise ValueError(f"site {site['site_no']}: no route from the link start to the SPBU")
    return entry, lib.bearing_along(pts, 0, 60), place_id


# --- one site ------------------------------------------------------------------

def leg_view(resp_leg, road_names=()):
    return {"distance_m": resp_leg.get("distanceMeters"),
            "duration_s": lib.parse_duration_s(resp_leg.get("duration")),
            "static_s": lib.parse_duration_s(resp_leg.get("staticDuration")),
            "maneuvers": lib.leg_maneuvers(resp_leg, road_names), "roads": lib.leg_roads(resp_leg),
            "polyline": (resp_leg.get("polyline") or {}).get("encodedPolyline", "")}


def csv_point(pt):
    """A (point, heading) pair rounded exactly as routes.csv stores it."""
    (lat, lng), h = pt
    return (round(lat, 7), round(lng, 7)), int(round(h)) % 360


def try_side(maps, pts, limits, allow_toll=False, accept=None, names=()):
    """One traffic-aware call for (entry, front, exit) = [(point, heading)] x3.

    Returns (ok, reasons, [leg views]).
    """
    (e, he), (f, hf), (x, hx) = pts
    resp = maps.traffic(wp(e, he), wp(f, hf, via=False), wp(x, hx))
    routes = resp.get("routes") or []
    if not routes or len(routes[0].get("legs", [])) != 2:
        msg = (resp.get("error") or {}).get("message", "no route")
        return False, [f"routes call failed: {msg[:120]}"], []
    legs = routes[0]["legs"]
    reasons = []
    for name, leg, o, d in (("approach", legs[0], e, f), ("departure", legs[1], f, x)):
        ok, why = lib.validate_leg(leg, o, d, f, limits, allow_toll, (accept or {}).get(name, ()), names)
        reasons += [f"{name}: {w}" for w in why]
    return not reasons, reasons, [leg_view(legs[0], names), leg_view(legs[1], names)]


SIDEWAYS_OFFSETS_M = (0, 8, 15, 25, 40, 60)   # steps across a median, to the other carriageway


def snap_on_road(maps, base, heading, across, names, offsets=SIDEWAYS_OFFSETS_M):
    """A point on the named road, travelling `heading`, found by stepping sideways from `base`.

    `across` is the compass bearing to step along. A candidate is accepted when the
    route from it starts within 25 m, on the named road, and stays on that road's first
    step for 200 m or more. Returns (snapped point, offset used) or (None, None).
    """
    for off in offsets:
        p = lib.dest_point(base, across, off) if off else base
        steps = _steps(maps.probe(wp(p, heading), wp(lib.dest_point(p, heading, 700))))
        if not steps:
            continue
        m, text, pts = _step_info(steps[0])
        road = lib.road_of_instruction(text)
        if (pts and m in ("", "DEPART") and steps[0].get("distanceMeters", 0) >= 200
                and lib.haversine_m(pts[0], p) <= 25
                and (not names or any(lib.road_matches(n, road) for n in names))):
            return pts[0], off
    return None, None


def derive_site(maps, site, pin, names, link, toll):
    """Return per-side results for one site: {side: {...}}."""
    target = lib.TOLL_TARGET_M if toll else lib.URBAN_TARGET_M
    limits = lib.TOLL_LIMITS_M if toll else lib.URBAN_LIMITS_M
    wanted = list(sides_for(site, toll))
    notes = []
    maps.avoid_tolls = not toll

    def fail(why, side=None):
        return {s: {"status": "needs_link", "note": why} for s in ([side] if side else wanted)}

    # 1. Where the road is and which way is the primary direction.
    exit_fixed = None
    if link:
        primary_side, url, exit_url = link
        start, heading, _ = link_anchor(maps, url, site)
        if exit_url:
            exit_fixed = lib.parse_directions_destination(exit_url)
        mode = "link"
    else:
        primary_side, mode = "spbu_side", "auto"
        if toll:
            return fail("toll site: needs a directions link")
        found = find_road_entry(maps, pin, names)
        if not found:
            return fail("no step onto the named road found near the pin")
        heading = lib.spbu_side_heading(found["bearing"], found["point"], pin)
        base = found["point"]
        notes.append(f"road found {found['dist_m']:.0f} m from pin ('{found['instruction'][:50]}')")

    # 2. Start the primary direction upstream: walk back along the far carriageway.
    if mode == "auto":
        far0, off = snap_on_road(maps, base, (heading + 180) % 360, (heading + 90) % 360, names)
        if not far0:
            return fail("no far carriageway found on the named road")
        back, _ = trace(maps, far0, (heading + 180) % 360, 200)
        if lib.path_length_m(back) < 100:
            return fail("could not trace upstream of the SPBU")
        h_up = (lib.bearing_along(back, 150) + 180) % 360
        # Walking back ran on the far carriageway: step toward the SPBU side to land on the near one.
        start, _ = snap_on_road(maps, lib.walk(back, 150), h_up, (h_up + 270) % 360, names,
                                (off,) + tuple(o for o in SIDEWAYS_OFFSETS_M if o != off))
        if not start:
            return fail("could not find the SPBU-side carriageway upstream")
        heading = h_up

    # 3. Primary-direction path past the SPBU gives Front and Exit.
    down, blocked = trace(maps, start, heading, lib.haversine_m(start, pin) + target + 150)
    if lib.path_length_m(down) < 60:
        return fail(f"could not trace the road ({blocked})")
    c_front, d_front, front = lib.nearest_on_path(down, pin)
    if lib.path_length_m(down) < c_front + target:
        down, blocked = trace(maps, start, heading, c_front + target + 50, down)
    h_front = lib.bearing_along(down, c_front)
    if (primary_side == "spbu_side") != lib.pin_on_left(front, h_front, pin):
        notes.append("link direction has the SPBU on the wrong side of travel: check the link")
    if d_front > FRONT_FAR_M:
        notes.append(f"Front is {d_front:.0f} m from the pin")

    # 4. Reverse direction from Front: the far carriageway (Opposite side) and upstream points.
    far, off = snap_on_road(maps, front, (h_front + 180) % 360, (h_front + 90) % 360, names)
    if not far:
        return fail("no far carriageway found on the named road: one-way road?")
    rev, blocked = trace(maps, far, (h_front + 180) % 360, target + 100)
    if lib.path_length_m(rev) < 100:
        return fail(f"could not trace the reverse direction ({blocked})")
    front_rev, h_front_rev = rev[0], lib.bearing_along(rev, 0)
    notes.append(f"far carriageway {lib.haversine_m(front, front_rev):.0f} m from Front")
    total_down, total_rev = lib.path_length_m(down), lib.path_length_m(rev)

    def forward_point(l_m):          # downstream of Front, primary direction
        c = min(c_front + l_m, total_down)
        return lib.walk(down, c), lib.bearing_along(down, c)

    def reverse_point(l_m):          # upstream of Front, from the reverse trace
        c = min(l_m, total_rev)
        return lib.walk(rev, c), (lib.bearing_along(rev, c) + 180) % 360

    sep = lib.haversine_m(front, front_rev)

    def on_carriageway(point, heading, across):
        """`point` moved onto the carriageway travelling `heading` (stepping toward `across`)."""
        offsets = tuple(dict.fromkeys([round(sep)] + list(SIDEWAYS_OFFSETS_M)))
        snapped, _ = snap_on_road(maps, point, heading, across, names, offsets)
        return (snapped or point), heading

    results = {}
    for side in wanted:
        primary = side == primary_side
        # (Approach length, Departure length, limits, keep the link's own Entry)
        plans = []
        override = LINK_ENTRY_SITES.get(site["site_no"], {})
        if mode == "link" and primary and (override or exit_fixed):
            plans.append((c_front, override.get("departure_m", target), (override.get("min_m", limits[0]), limits[1]), True))
        if mode == "link" and primary and 0.85 * target <= c_front <= 1.3 * target:
            plans.append((c_front, target, limits, True))
        plans += [(a * target, b * target, limits, False) for a, b in VARIANTS]
        if not toll:
            plans += [(a * target, b * target, (SHORT_LIMIT_M, limits[1]), False)
                      for a, b in SHORT_VARIANTS]
        attempts = []
        for l_in, l_out, lim, keep_link_entry in plans:
            if primary:
                if keep_link_entry:
                    entry_pt = (start, heading)
                elif mode == "link" and c_front > l_in + 10:
                    entry_pt = (lib.walk(down, c_front - l_in), lib.bearing_along(down, c_front - l_in))
                else:       # the reverse trace runs on the far carriageway: cross back to ours
                    p, h = reverse_point(l_in)
                    entry_pt = on_carriageway(p, h, (h + 270) % 360)
                pts = [entry_pt, (front, h_front), forward_point(l_out)]
            else:           # the forward trace runs on our carriageway: cross to the far one
                p, h = forward_point(l_in)
                h = (h + 180) % 360
                exit_pt = reverse_point(l_out)
                pts = [on_carriageway(p, h, (h + 270) % 360), (front_rev, h_front_rev),
                       (exit_pt[0], (exit_pt[1] + 180) % 360)]
            use_link_plan = primary and keep_link_entry
            if use_link_plan and exit_fixed:
                pts[2] = (exit_fixed, lib.bearing_deg(front, exit_fixed))
            pts = [csv_point(p) for p in pts]
            accept = override.get("accept") if override and use_link_plan else None
            ok, reasons, legs = try_side(maps, pts, lim, toll, accept, names)
            attempts.append((pts, ok, reasons, legs, lim != limits))
            if ok:
                break
        pts, ok, reasons, legs, relaxed = attempts[-1]
        note = list(notes)
        if ok and relaxed:
            note.append("short leg: " + "/".join(str(lg["distance_m"]) for lg in legs) + " m")
        other = [r for lg in legs for r in lg["roads"] if not any(lib.road_matches(n, r) for n in names)]
        if ok and other:
            note.append("legs also run on " + ", ".join(dict.fromkeys(other)))
        if ok and len(attempts) > 1:
            note.append(f"variant {len(attempts)} of {len(plans)}; {int(target)} m failed: "
                        + "; ".join(attempts[0][2]))
        if not ok:
            note.append("needs a directions link: " + "; ".join(attempts[0][2] or reasons))
        results[side] = {"status": "ok" if ok else "needs_link", "pts": pts, "legs": legs,
                         "front_from_pin_m": d_front if primary else lib.haversine_m(pts[1][0], pin),
                         "note": "; ".join(note), "attempts": len(attempts)}
    return results


# --- files ---------------------------------------------------------------------

def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def site_id_of(site):
    return site["spbu_code"]


def route_id(site, side, leg):
    sid = site_id_of(site).replace(".", "")
    return f"spbu-{sid}-{'spbuside' if side == 'spbu_side' else 'opposite'}-{leg}"


def side_rows(site, side, res):
    """The two routes.csv rows (Approach, Departure) for one side."""
    rows = []
    pts = res.get("pts")
    legs = res.get("legs") or [{}, {}]
    call_id = f"spbu-{site_id_of(site).replace('.', '')}-{'spbuside' if side == 'spbu_side' else 'opposite'}"
    for i, leg in enumerate(("approach", "departure")):
        row = {c: "" for c in ROUTES_COLUMNS}
        row.update(selected_route_id=route_id(site, side, leg), site_no=site["site_no"],
                   site_id=site_id_of(site), side=side, leg=leg, call_id=call_id, leg_index=i,
                   status=res["status"], note=res.get("note", ""))
        if pts:
            (o, ho), (d, hd) = (pts[0], pts[1]) if i == 0 else (pts[1], pts[2])
            row.update(origin_lat=f"{o[0]:.7f}", origin_lng=f"{o[1]:.7f}", origin_heading=int(round(ho)) % 360,
                       dest_lat=f"{d[0]:.7f}", dest_lng=f"{d[1]:.7f}", dest_heading=int(round(hd)) % 360)
        if i < len(legs) and legs[i].get("distance_m") is not None:
            row["expected_distance_m"] = legs[i]["distance_m"]
            row["expected_polyline"] = legs[i].get("polyline", "")
        rows.append(row)
    return rows


def main():
    sites = read_csv(SITES_CSV)
    links = {(r["site_no"], r["side"]): (r["entry_url"], r["exit_url"]) for r in read_csv(LINKS_CSV)}
    maps = Maps(get_api_key())
    rows, polylines = [], {}
    for site in sites:
        no = site["site_no"]
        toll = "toll" in site["road_type"].lower()
        details = maps.place(site["place_id"])
        results = {}
        if "location" in details:
            pin = lib.latlng(details["location"])
            routes_named = [c.get("longText", "") for c in details.get("addressComponents", [])
                            if "route" in c.get("types", [])]
            names = [site["road"]] + [r for r in routes_named if r]
            link_list = [(s, *links[(no, s)]) for s in SIDES if (no, s) in links]
            runs = link_list or [None]
        else:
            why = f"Places lookup failed: {details.get('error', {}).get('message', '')[:100]}"
            results = {s: {"status": "needs_link", "note": why} for s in sides_for(site, toll)}
            runs = []
        for link in runs:
            try:
                part = derive_site(maps, site, pin, names, link, toll)
            except ValueError as e:      # e.g. a link for the wrong place
                part = {s: {"status": "needs_link", "note": f"link rejected: {e}"}
                        for s in sides_for(site, toll)}
            for side, res in part.items():
                # An explicit link for a side wins over a mirrored result for it.
                if side not in results or (link and link[0] == side):
                    results[side] = res
        for side in sides_for(site, toll):
            res = results.get(side) or {"status": "needs_link", "note": "no result"}
            rows += side_rows(site, side, res)
            for i, leg in enumerate(("approach", "departure")):
                lv = (res.get("legs") or [{}, {}])[i] if res.get("legs") else {}
                polylines[route_id(site, side, leg)] = dict(
                    lv, front_from_pin_m=res.get("front_from_pin_m"), status=res["status"])
            print(f"site {no:>2} {side:<9} {res['status']:<10} "
                  + " / ".join(str((lg or {}).get('distance_m')) for lg in (res.get('legs') or []))
                  + f"  {res.get('note', '')[:110]}")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(ROUTES_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, ROUTES_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with open(POLYLINES_JSON, "w") as f:
        json.dump(polylines, f)
    print(f"wrote {len(rows)} rows to {os.path.relpath(ROUTES_CSV, ROOT)}; "
          f"calls made this run {maps.made}, from cache {maps.cached}")


if __name__ == "__main__":
    main()
