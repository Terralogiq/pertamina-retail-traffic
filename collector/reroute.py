"""Pure reroute check. A leg is rerouted when the returned distance is more than 10% longer or shorter
than the expected route distance, or the returned polyline leaves a 30 m buffer around the expected polyline.
"""
import math

EARTH_R = 6371000.0


def _haversine_m(a, b):
    """a and b are (lat, lng) tuples."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def _densify(pts, step_m=5.0):
    """Insert points so consecutive points are at most `step_m` apart."""
    out = []
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(_haversine_m(a, b) // step_m))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    return out + [pts[-1]] if pts else []


def _leaves_buffer(actual_pts, expected_pts, buffer_m=30.0):
    """True when any point on the actual polyline is more than `buffer_m` from the expected polyline."""
    if not actual_pts or not expected_pts:
        return False
    dense = _densify(expected_pts, step_m=buffer_m / 2)
    for p in actual_pts:
        if min(_haversine_m(p, q) for q in dense) > buffer_m:
            return True
    return False


def is_rerouted(expected_distance_m, actual_distance_m, actual_polyline, expected_polyline, buffer_m=30.0):
    """
    A leg is rerouted when:
      - actual_distance_m is more than 10% longer or shorter than expected_distance_m, or
      - actual_polyline leaves a `buffer_m` corridor around expected_polyline.
    Missing values never flag a reroute.
    """
    if expected_distance_m is None or expected_distance_m <= 0:
        return False
    if actual_distance_m is not None and abs(actual_distance_m - expected_distance_m) > 0.1 * expected_distance_m:
        return True
    if not actual_polyline or not expected_polyline:
        return False
    return _leaves_buffer(actual_polyline, expected_polyline, buffer_m)
