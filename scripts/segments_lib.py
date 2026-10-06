"""Pure helpers for placing and validating the Entry/Front/Exit segments.

No network, no key, no file access at import time. Used by
scripts/propose_segments.py and scripts/preview_segments.py.

Conventions: a point is a (lat, lng) tuple in degrees; distances are metres;
bearings are compass degrees (0 = north, clockwise). Indonesia drives on the
LEFT, so the SPBU side of a road is the direction of travel with the station on
the driver's left.
"""
import base64
import math
import re
import struct

EARTH_R = 6371000.0

# Leg length targets and limits (metres), from docs/plans/collector.md.
URBAN_TARGET_M = 500
TOLL_TARGET_M = 1000
URBAN_LIMITS_M = (400, 700)
TOLL_LIMITS_M = (500, 1300)
MAX_DETOUR = 1.15          # leg length / straight-line distance
SNAP_TOL_M = 30            # request point vs where Routes snapped it
BAD_MANEUVER_PREFIXES = ("UTURN", "RAMP", "TURN", "ROUNDABOUT")


# --- polyline and geometry ---------------------------------------------------

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


def haversine_m(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def bearing_deg(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def dest_point(p, brg, m):
    """Point `m` metres from `p` along compass bearing `brg`."""
    d = m / EARTH_R
    t = math.radians(brg)
    p1, l1 = math.radians(p[0]), math.radians(p[1])
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(t))
    l2 = l1 + math.atan2(math.sin(t) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return (math.degrees(p2), math.degrees(l2))


def angle_diff(a, b):
    """Smallest absolute difference between two bearings, 0..180."""
    return abs((a - b + 180) % 360 - 180)


def densify(pts, step_m=5.0):
    """Insert points so consecutive points are at most `step_m` apart."""
    out = []
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(haversine_m(a, b) // step_m))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                for k in range(n)]
    return out + [pts[-1]] if pts else []


def cumulative_m(pts):
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + haversine_m(a, b))
    return cum


def path_length_m(pts):
    return cumulative_m(pts)[-1] if pts else 0.0


def walk(pts, m):
    """Point `m` metres along the polyline (clamped to its end)."""
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = haversine_m(a, b)
        if d > 0 and acc + d >= m:
            f = (m - acc) / d
            return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
        acc += d
    return pts[-1]


def nearest_on_path(pts, p, step_m=5.0):
    """(chainage_m, distance_m, point) of the point on the polyline nearest `p`."""
    dense = densify(pts, step_m)
    cum = cumulative_m(dense)
    k = min(range(len(dense)), key=lambda i: haversine_m(dense[i], p))
    return cum[k], haversine_m(dense[k], p), dense[k]


def bearing_along(pts, chainage_m, span_m=30.0):
    """Travel bearing of the polyline around `chainage_m` (+/- span_m)."""
    total = path_length_m(pts)
    a = walk(pts, max(0.0, chainage_m - span_m))
    b = walk(pts, min(total, chainage_m + span_m))
    return bearing_deg(a, b)


def min_distance_to_path_m(pts, p, step_m=5.0):
    return nearest_on_path(pts, p, step_m)[1]


# --- left-hand traffic -------------------------------------------------------

def pin_on_left(front, heading, pin):
    """True if `pin` is on the driver's left when travelling `heading` at `front`."""
    rel = math.radians(bearing_deg(front, pin) - heading)
    return math.sin(rel) < 0


def spbu_side_heading(road_bearing, front, pin):
    """Travel direction (of the two along the road) with the station on the left."""
    if pin_on_left(front, road_bearing, pin):
        return road_bearing % 360
    return (road_bearing + 180) % 360


# --- Google Maps directions link ---------------------------------------------

_START_RE = re.compile(r"/dir/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/")
_DEST_RE = re.compile(r"/dir/[^/]+/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/")
_FID_RE = re.compile(r"!1s(0x[0-9a-fA-F]+):(0x[0-9a-fA-F]+)")


def fid_to_place_id(hex1, hex2):
    """Feature ID halves ('0x..', '0x..') to a Places place_id."""
    raw = struct.pack("<Q", int(hex1, 16)) + b"\x11" + struct.pack("<Q", int(hex2, 16))
    return "ChIJ" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def parse_directions_url(url):
    """Return ((lat, lng) of the link's start, place_id) from a directions link."""
    m = _START_RE.search(url)
    f = _FID_RE.search(url)
    if not m or not f:
        raise ValueError("not a directions link with a start point and a place ID")
    return (float(m.group(1)), float(m.group(2))), fid_to_place_id(f.group(1), f.group(2))


def parse_directions_destination(url):
    """Return the (lat, lng) destination of a '/dir/<place>/<lat>,<lng>/' link (the SPBU -> Exit link)."""
    m = _DEST_RE.search(url)
    if not m:
        raise ValueError("not a directions link with a destination coordinate after the place")
    return float(m.group(1)), float(m.group(2))


# --- road names --------------------------------------------------------------

def norm_road(s):
    s = (s or "").lower()
    s = re.sub(r"\b(jalan|jl)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(p|pangeran|dr|h|k\.?h)\b", " ", s)
    return " ".join(s.split())


def road_matches(wanted, seen):
    """True if road name `seen` is the road `wanted` (every token of the shorter name is in the other).

    `seen` may list aliases joined by '/', as Routes step instructions do; any alias can match.
    """
    a = norm_road(wanted)
    if not a:
        return False
    for alias in (seen or "").split("/"):
        b = norm_road(alias)
        if not b:
            continue
        ta, tb = set(a.split()), set(b.split())
        short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        if short <= long_ or a.replace(" ", "") in b.replace(" ", "") or b.replace(" ", "") in a.replace(" ", ""):
            return True
    return False


def road_of_instruction(text):
    """Road named by a step instruction: text after the last ' on ' / ' onto '."""
    lines = (text or "").splitlines()
    first = lines[0] if lines else ""
    m = re.search(r"\b(?:onto|on|ke|di)\s+(.+?)(?:\s+toward\b|\s+menuju\b|$)", first)
    return m.group(1).strip() if m else ""


# --- Routes API response parsing ---------------------------------------------

def parse_duration_s(v):
    """'123s' -> 123.0 (None stays None)."""
    if v is None:
        return None
    return float(str(v).rstrip("s"))


def latlng(loc):
    """{'latLng': {'latitude':..,'longitude':..}} or {'latitude':..} -> (lat, lng)."""
    if loc is None:
        return None
    loc = loc.get("latLng", loc)
    return (loc["latitude"], loc["longitude"])


def is_keep_on_road(instructions, road_names=()):
    """True for a lane split that stays on the same road ("Keep left to continue on X").

    Routes codes these as TURN_LEFT/RIGHT, but the driver doesn't turn (site 3, user 2026-10-06).
    Only counts when X is one of `road_names`; without names nothing is dropped.
    """
    t = (instructions or "").strip().lower()
    if not t.startswith(("keep left", "keep right")) or "continue on" not in t:
        return False
    road = road_of_instruction(instructions)
    return bool(road) and any(road_matches(n, road) for n in road_names)


def leg_maneuvers(leg, road_names=()):
    """Maneuvers of a leg's steps, in order, excluding DEPART, empty ones and keep-on-road splits."""
    out = []
    for st in leg.get("steps", []):
        ni = st.get("navigationInstruction") or {}
        m = ni.get("maneuver")
        if m and m != "DEPART" and not is_keep_on_road(ni.get("instructions"), road_names):
            out.append(m)
    return out


def leg_roads(leg):
    """Road names the leg's step instructions mention, in order, without repeats."""
    roads = []
    for st in leg.get("steps", []):
        r = road_of_instruction((st.get("navigationInstruction") or {}).get("instructions", ""))
        if r and r not in roads:
            roads.append(r)
    return roads


def leg_on_toll(leg):
    """True if a step instruction marks the leg as running on a toll road."""
    return any("toll road" in ((st.get("navigationInstruction") or {}).get("instructions", "")).lower()
               for st in leg.get("steps", []))


def leg_polyline(leg):
    enc = (leg.get("polyline") or {}).get("encodedPolyline")
    return decode_polyline(enc) if enc else []


def validate_leg(leg, origin, dest, front, limits=URBAN_LIMITS_M, allow_toll=False, accepted=(),
                 road_names=()):
    """Check one parsed leg of a computeRoutes response.

    `origin`/`dest` are the requested end points of this leg, `front` the Front
    point. `accepted` lists maneuvers a user verified on the map as not being turns;
    `road_names` are the site's road names, for telling a keep-on-road split from a real turn.
    Returns (ok, reasons); `reasons` lists every failed check.
    """
    reasons = []
    dist = leg.get("distanceMeters")
    if dist is None:
        return False, ["no distance"]
    lo, hi = limits
    if not lo <= dist <= hi:
        reasons.append(f"length {dist} m outside {lo}-{hi} m")
    straight = haversine_m(origin, dest)
    if straight > 0 and dist > MAX_DETOUR * straight:
        reasons.append(f"length {dist} m is {dist / straight:.2f}x the straight line {straight:.0f} m")
    if not allow_toll and leg_on_toll(leg):
        reasons.append("leg runs on a toll road")
    bad = [m for m in leg_maneuvers(leg, road_names) if m.startswith(BAD_MANEUVER_PREFIXES) and m not in accepted]
    if bad:
        reasons.append("maneuvers " + ",".join(bad))
    s, e = latlng(leg.get("startLocation")), latlng(leg.get("endLocation"))
    if s and haversine_m(s, origin) > SNAP_TOL_M:
        reasons.append(f"start snapped {haversine_m(s, origin):.0f} m from the request point")
    if e and haversine_m(e, dest) > SNAP_TOL_M:
        reasons.append(f"end snapped {haversine_m(e, dest):.0f} m from the request point")
    path = leg_polyline(leg)
    if path and min_distance_to_path_m(path, front) > SNAP_TOL_M:
        reasons.append(f"polyline misses Front by {min_distance_to_path_m(path, front):.0f} m")
    return not reasons, reasons
