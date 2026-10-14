"""Unit tests for collector/bq.py and main.exit_code (pure: no google.cloud, no network)."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "collector"))

import bq  # noqa: E402
import main  # noqa: E402


def traffic_sql():
    return bq.merge_sql("p.d.traffic_snapshots", "p.d._stg", bq.TRAFFIC_STAGE, bq.TRAFFIC_KEYS,
                        bq.TRAFFIC_INSERT_ONLY, bq.TRAFFIC_GUARD)


def weather_sql():
    return bq.merge_sql("p.d.weather_slots", "p.d._stg", bq.WEATHER_STAGE, bq.WEATHER_KEYS,
                        None, bq.WEATHER_GUARD)


def parts(sql):
    """(ON clause, MATCHED branch, NOT MATCHED branch)."""
    on = sql.split("\nON ")[1].split("\nWHEN MATCHED")[0]
    matched = sql.split("\nWHEN MATCHED")[1].split("\nWHEN NOT MATCHED")[0]
    not_matched = sql.split("\nWHEN NOT MATCHED")[1]
    return on, matched, not_matched


class TestImports(unittest.TestCase):
    def test_google_cloud_not_imported(self):
        self.assertFalse([m for m in sys.modules if m == "google.cloud" or m.startswith("google.cloud.")])


class TestMergeSql(unittest.TestCase):
    def test_on_clause_has_keys_and_slot_prune(self):
        for sql, keys in ((traffic_sql(), bq.TRAFFIC_KEYS), (weather_sql(), bq.WEATHER_KEYS)):
            on, _, _ = parts(sql)
            for k in keys:
                self.assertIn(f"T.{k} = S.{k}", on)
            self.assertIn("T.slot_time = @slot_time", on)

    def test_update_excludes_key_columns(self):
        for sql, keys in ((traffic_sql(), bq.TRAFFIC_KEYS), (weather_sql(), bq.WEATHER_KEYS)):
            _, matched, _ = parts(sql)
            set_cols = re.findall(r"(\w+) = ", matched.split("UPDATE SET", 1)[1])
            for k in keys:
                self.assertNotIn(k, set_cols)
            self.assertIn("fetched_at", set_cols)

    def test_insert_only_arrays_only_in_insert_branch(self):
        sql = traffic_sql()
        _, matched, not_matched = parts(sql)
        for col, literal in bq.TRAFFIC_INSERT_ONLY.items():
            self.assertNotIn(literal, matched)
            self.assertNotIn(col, matched)
            self.assertIn(literal, not_matched)
            self.assertIn(col, not_matched)
        self.assertEqual(sql.count("ARRAY<STRING>[]"), 1)

    def test_weather_has_no_insert_only_columns(self):
        self.assertNotIn("ARRAY<", weather_sql())

    def test_geometry_and_raw_wrapped(self):
        sql = traffic_sql()
        self.assertEqual(sql.count("SAFE.ST_GEOGFROMTEXT(S.route_geometry)"), 2)  # UPDATE and INSERT
        self.assertNotIn("S.route_geometry,", sql.replace("SAFE.ST_GEOGFROMTEXT(S.route_geometry)", ""))
        self.assertEqual(sql.count("PARSE_JSON(S.raw"), 2)
        self.assertEqual(weather_sql().count("PARSE_JSON(S.raw"), 2)
        self.assertNotIn("ST_GEOGFROMTEXT", weather_sql())


class TestGuard(unittest.TestCase):
    def test_traffic_guard(self):
        _, matched, _ = parts(traffic_sql())
        self.assertTrue(matched.startswith(
            " AND (S.duration_in_seconds IS NOT NULL OR T.duration_in_seconds IS NULL) THEN UPDATE SET"))

    def test_weather_guard(self):
        _, matched, _ = parts(weather_sql())
        self.assertTrue(matched.startswith(
            " AND (S.temperature_c IS NOT NULL OR T.temperature_c IS NULL) THEN UPDATE SET"))

    def test_no_guard_by_default(self):
        sql = bq.merge_sql("t", "s", bq.WEATHER_STAGE, bq.WEATHER_KEYS)
        self.assertIn("\nWHEN MATCHED THEN UPDATE SET", sql)

    def test_guard_only_on_matched_branch(self):
        _, _, not_matched = parts(traffic_sql())
        self.assertNotIn("IS NOT NULL", not_matched)

    def test_write_rows_use_guards(self):
        self.assertEqual(bq.TRAFFIC_GUARD, "duration_in_seconds")
        self.assertEqual(bq.WEATHER_GUARD, "temperature_c")
        self.assertIn(bq.TRAFFIC_GUARD, [c for c, _ in bq.TRAFFIC_STAGE])
        self.assertIn(bq.WEATHER_GUARD, [c for c, _ in bq.WEATHER_STAGE])


class TestCheckUnique(unittest.TestCase):
    KEYS = ("site_id", "slot_time")

    def test_unique_passes(self):
        bq.check_unique([{"site_id": "a", "slot_time": 1}, {"site_id": "b", "slot_time": 1},
                         {"site_id": "a", "slot_time": 2}], self.KEYS)

    def test_duplicate_raises(self):
        rows = [{"site_id": "a", "slot_time": 1}, {"site_id": "a", "slot_time": 1}]
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            bq.check_unique(rows, self.KEYS)

    def test_empty_passes(self):
        bq.check_unique([], self.KEYS)


class TestLinePoints(unittest.TestCase):
    def test_geojson_lng_lat_becomes_lat_lng(self):
        g = '{"type":"LineString","coordinates":[[105.32234,-5.41371],[105.3198296,-5.4101864]]}'
        self.assertEqual(bq.line_points(g), [(-5.41371, 105.32234), (-5.4101864, 105.3198296)])

    def test_not_a_line_is_empty(self):
        self.assertEqual(bq.line_points(None), [])
        self.assertEqual(bq.line_points('{"type":"Point","coordinates":[105.3,-5.4]}'), [])

    def test_routes_sql_returns_geojson(self):
        self.assertIn("ST_ASGEOJSON(expected_polyline) AS expected_geojson", bq.ROUTES_SQL)


class TestLoadRoutesCsv(unittest.TestCase):
    def test_expected_points_decoded_from_csv(self):
        routes = main.load_routes_csv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                   "data", "routes.csv"))
        self.assertTrue(routes)
        for r in routes:
            self.assertGreaterEqual(len(r["expected_points"]), 2)
            for lat, lng in r["expected_points"]:
                self.assertTrue(-11 < lat < 6 and 95 < lng < 141, (lat, lng))


class TestExitCode(unittest.TestCase):
    def test_no_calls_is_failure(self):
        self.assertEqual(main.exit_code(0, 0), 1)

    def test_all_failed_is_failure(self):
        self.assertEqual(main.exit_code(5, 5), 1)

    def test_partial_failure_is_ok(self):
        self.assertEqual(main.exit_code(5, 4), 0)

    def test_no_failures_is_ok(self):
        self.assertEqual(main.exit_code(5, 0), 0)


if __name__ == "__main__":
    unittest.main()
