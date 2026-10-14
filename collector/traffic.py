"""Traffic: one Routes `computeRoutes` call per call_id gives both legs of a site.

The call runs Entry -> Front -> Exit, with Front as a `via: false` stop, so the response
splits at Front into the Approach leg (leg_index 0) and the Departure leg (leg_index 1).
Pure functions plus one HTTP wrapper (`fetch_call`); no google.cloud import.

A "route" below is a dict with: selected_route_id, display_name, site_id, side, call_id,
leg_index, origin_lat, origin_lng, origin_heading, dest_lat, dest_lng, dest_heading,
expected_distance_m (headings and distance may be None).
"""
import json
from collections import defaultdict

import httpjson
from reroute import is_rerouted
from slots import iso, utc_now

API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = ("routes.legs.distanceMeters,routes.legs.duration,routes.legs.staticDuration,"
              "routes.legs.polyline.encodedPolyline")
ROUTING_PREFERENCE = "TRAFFIC_AWARE"


# --- parsing helpers (copied from scripts/segments_lib.py: the image only has collector/) ---

def parse_duration_s(v):
    """'123s' -> 123.0 (None stays None)."""
    if v is None:
        return None
    return float(str(v).rstrip("s"))


def decode_polyline(s):
    """Decode a Google encoded polyline (precision 5) to [(lat, lng), ...]."""
    pts, i, lat, lng = [], 0, 0, 0
    while i < len(s):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += delta
            else:
                lng += delta
        pts.append((lat / 1e5, lng / 1e5))
    return pts


def polyline_to_wkt(encoded):
    """Encoded polyline -> 'LINESTRING(lng lat, ...)', or None with fewer than 2 distinct points.

    WKT is x y = lng lat. Repeated consecutive points are dropped: BigQuery rejects
    a degenerate (zero-length) edge.
    """
    if not encoded:
        return None
    pts = []
    for p in decode_polyline(encoded):
        if not pts or p != pts[-1]:
            pts.append(p)
    if len(pts) < 2:
        return None
    return "LINESTRING(" + ", ".join(f"{lng:.5f} {lat:.5f}" for lat, lng in pts) + ")"


# --- request ---

def group_calls(routes):
    """{call_id: [route, ...]} with each call's legs ordered by leg_index."""
    calls = defaultdict(list)
    for r in routes:
        calls[r["call_id"]].append(r)
    return {cid: sorted(legs, key=lambda r: r["leg_index"]) for cid, legs in sorted(calls.items())}


def waypoint(lat, lng, heading=None, via=None):
    loc = {"latLng": {"latitude": lat, "longitude": lng}}
    if heading is not None:
        loc["heading"] = int(heading) % 360
    wp = {"location": loc}
    if via is not None:
        wp["via"] = via
    return wp


def build_request(legs):
    """computeRoutes body for one call_id: Entry -> Front (stop) -> Exit."""
    if [r["leg_index"] for r in legs] != [0, 1]:
        raise ValueError(f"call {legs[0]['call_id'] if legs else '?'} needs legs 0 and 1, "
                         f"got {[r['leg_index'] for r in legs]}")
    approach, departure = legs
    return {
        "origin": waypoint(approach["origin_lat"], approach["origin_lng"], approach["origin_heading"]),
        "intermediates": [waypoint(approach["dest_lat"], approach["dest_lng"], approach["dest_heading"], via=False)],
        "destination": waypoint(departure["dest_lat"], departure["dest_lng"], departure["dest_heading"]),
        "travelMode": "DRIVE",
        "routingPreference": ROUTING_PREFERENCE,
    }


# --- response -> rows ---

def response_legs(resp):
    """(legs, None) from a computeRoutes response, or (None, reason)."""
    routes = (resp or {}).get("routes") or []
    if not routes:
        return None, "no route in response"
    legs = routes[0].get("legs") or []
    if len(legs) != 2:
        return None, f"expected 2 legs, got {len(legs)}"
    return legs, None


def leg_row(route, leg, slot, fetched_at, request, error=None):
    """One traffic_snapshots row (JSON-ready dict). `leg` is {} when the call failed."""
    duration = parse_duration_s(leg.get("duration"))
    static = parse_duration_s(leg.get("staticDuration"))
    expected = route.get("expected_distance_m")
    actual_distance = leg.get("distanceMeters")
    actual_polyline = decode_polyline((leg.get("polyline") or {}).get("encodedPolyline", ""))
    expected_polyline = decode_polyline(route.get("expected_polyline") or "")
    rerouted = None if error else is_rerouted(
        expected,
        int(actual_distance) if actual_distance is not None else None,
        actual_polyline,
        expected_polyline,
    )
    raw = {"request": request, "error": error} if error else {"request": request, "leg": leg}
    return {
        "selected_route_id": route["selected_route_id"],
        "display_name": route.get("display_name"),
        "record_time": iso(fetched_at),
        "duration_in_seconds": duration,
        "static_duration_in_seconds": static,
        "route_geometry": polyline_to_wkt((leg.get("polyline") or {}).get("encodedPolyline")),
        "road_segment_ids": [],
        "speed_reading_intervals": [],
        "slot_time": iso(slot),
        "static_ratio": duration / static if duration is not None and static else None,
        "speed_kmh": expected / duration * 3.6 if expected is not None and duration else None,
        "demo_distance_m": int(actual_distance) if actual_distance is not None else None,
        "demo_rerouted": rerouted,
        "demo_routing_preference": ROUTING_PREFERENCE,
        "raw": json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
        "fetched_at": iso(fetched_at),
    }


def call_rows(legs, resp, error, slot, fetched_at, request):
    """(rows, error) for one call. A failed call (`error` set or an unusable response) still
    yields one row per leg, with null durations and the reason in raw."""
    resp_legs = None
    if not error:
        resp_legs, error = response_legs(resp)
    if error:
        return [leg_row(r, {}, slot, fetched_at, request, error) for r in legs], error
    return [leg_row(r, leg, slot, fetched_at, request) for r, leg in zip(legs, resp_legs)], None


def fetch_call(key, legs, slot):
    """Call computeRoutes for one call_id. Returns (rows, error); error is None on success. Never raises."""
    request = None
    try:
        request = build_request(legs)
        resp, error = httpjson.request_json(
            "POST", API_URL, {"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK},
            request, secret=key)
        return call_rows(legs, resp, error, slot, utc_now(), request)
    except Exception as e:  # noqa: BLE001 - one bad call must not drop the slot
        error = f"{type(e).__name__}: {str(e).replace(key, '***')}"
        return [leg_row(r, {}, slot, utc_now(), request, error) for r in legs], error
