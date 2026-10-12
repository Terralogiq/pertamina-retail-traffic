"""Unit tests for the pure helpers in scripts/load_reference.py. No network, no BigQuery."""
import importlib.util
import os
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
_spec = importlib.util.spec_from_file_location("load_reference", os.path.join(SCRIPTS, "load_reference.py"))
lr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lr)

# Google's documented example: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
POLY = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"

SITE = {"spbu_code": "34.121.03", "road": "Jl. TB Simatupang", "road_type": "congested arterial",
        "city": "Jakarta Selatan", "place_id": "ChIJabc", "timezone": "Asia/Jakarta"}
ROUTE = {
    "selected_route_id": "spbu-3412103-spbuside-approach", "site_id": "34.121.03",
    "side": "spbu_side", "leg": "approach", "call_id": "spbu-3412103-spbuside", "leg_index": "0",
    "origin_lat": "-6.2926129", "origin_lng": "106.8158840", "origin_heading": "270",
    "dest_lat": "-6.2923962", "dest_lng": "106.8117085", "dest_heading": "268",
    "expected_distance_m": "500", "expected_polyline": POLY, "status": "ok", "note": "",
}


class WktTest(unittest.TestCase):
    def test_point_is_lng_lat(self):
        self.assertEqual(lr.point_wkt("-6.5", "106.25"), "POINT(106.2500000 -6.5000000)")

    def test_linestring_from_decoded_polyline(self):
        pts = lr.lib.decode_polyline(POLY)
        self.assertEqual(
            lr.linestring_wkt(pts),
            "LINESTRING(-120.2000000 38.5000000, -120.9500000 40.7000000, -126.4530000 43.2520000)")


class MidPointTest(unittest.TestCase):
    def test_midpoint_of_straight_line(self):
        pts = [(0.0, 100.0), (0.0, 100.01)]
        lat, lng = lr.mid_point(pts)
        self.assertAlmostEqual(lat, 0.0, places=6)
        self.assertAlmostEqual(lng, 100.005, places=6)

    def test_midpoint_splits_length_in_half(self):
        # Short two-segment path (~300 m then ~100 m): the midpoint is 200 m along, on the first segment.
        pts = [(0.0, 100.0), (0.0, 100.0027), (0.0009, 100.0027)]
        total = lr.lib.path_length_m(pts)
        mid = lr.mid_point(pts)
        self.assertAlmostEqual(lr.lib.haversine_m(pts[0], mid), total / 2, delta=1.0)


class RowsTest(unittest.TestCase):
    def test_display_name(self):
        self.assertEqual(lr.display_name(SITE, ROUTE),
                         "SPBU 34.121.03 Jl. TB Simatupang · SPBU side · Approach")
        dep = dict(ROUTE, leg="departure", side="opposite")
        self.assertEqual(lr.display_name(SITE, dep),
                         "SPBU 34.121.03 Jl. TB Simatupang · Opposite side · Departure")

    def test_route_row(self):
        r = lr.route_row(ROUTE, SITE)
        self.assertEqual(r["selected_route_id"], "spbu-3412103-spbuside-approach")
        self.assertEqual(r["origin_wkt"], "POINT(106.8158840 -6.2926129)")
        self.assertEqual(r["destination_wkt"], "POINT(106.8117085 -6.2923962)")
        self.assertTrue(r["expected_wkt"].startswith("LINESTRING(-120.2000000 38.5000000"))
        self.assertTrue(r["mid_wkt"].startswith("POINT("))
        self.assertEqual((r["leg_index"], r["expected_distance_m"]), (0, 500))
        self.assertEqual((r["demo_origin_heading"], r["demo_dest_heading"]), (270, 268))
        self.assertIs(r["active"], True)

    def test_inactive_when_status_not_ok(self):
        self.assertIs(lr.route_row(dict(ROUTE, status="needs_link"), SITE)["active"], False)

    def test_short_polyline_rejected(self):
        with self.assertRaises(ValueError):
            lr.route_row(dict(ROUTE, expected_polyline="_p~iF~ps|U"), SITE)

    def test_build_route_rows_joins_site(self):
        rows = lr.build_route_rows([ROUTE], [SITE])
        self.assertEqual(len(rows), 1)
        self.assertIn("Jl. TB Simatupang", rows[0]["display_name"])

    def test_site_row(self):
        details = {"displayName": {"text": "SPBU X"}, "location": {"latitude": -6.29, "longitude": 106.81}}
        r = lr.site_row(SITE, details)
        self.assertEqual(r, {"site_id": "34.121.03", "name": "SPBU X", "place_id": "ChIJabc",
                             "location_wkt": "POINT(106.8100000 -6.2900000)",
                             "road_name": "Jl. TB Simatupang", "city": "Jakarta Selatan",
                             "road_type": "congested arterial", "timezone": "Asia/Jakarta"})

    def test_site_row_carries_timezone(self):
        r = lr.site_row(dict(SITE, timezone="Asia/Makassar"), {})
        self.assertEqual(r["timezone"], "Asia/Makassar")

    def test_sites_csv_timezones(self):
        zones = {s["city"]: s["timezone"] for s in lr.read_csv(lr.SITES_CSV)}
        self.assertEqual({c for c, z in zones.items() if z == "Asia/Makassar"},
                         {"Balikpapan", "Makassar", "Denpasar"})
        self.assertEqual(set(zones.values()), {"Asia/Jakarta", "Asia/Makassar"})
        self.assertIn("timezone", lr.SITES_SCHEMA)
        self.assertIn("timezone", lr.MERGE_SITES)
        self.assertIn("road_type", lr.SITES_SCHEMA)
        self.assertIn("road_type", lr.MERGE_SITES)

    def test_sites_csv_road_class(self):
        """KM57A is the only toll site; the word toll in road_type is the rule."""
        rows = lr.read_csv(lr.SITES_CSV)
        toll = [s["spbu_code"] for s in rows if "toll" in s["road_type"].lower()]
        self.assertEqual(toll, ["KM57A"])
        self.assertEqual(len(rows), 10)

    def test_site_row_without_details(self):
        r = lr.site_row(SITE, {})
        self.assertIsNone(r["name"])
        self.assertIsNone(r["location_wkt"])


if __name__ == "__main__":
    unittest.main()
