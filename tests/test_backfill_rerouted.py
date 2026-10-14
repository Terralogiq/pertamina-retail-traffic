"""Unit tests for scripts/backfill_rerouted.py pure helpers (no google.cloud, no network)."""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import backfill_rerouted as bf  # noqa: E402
from reroute import is_rerouted  # noqa: E402

# Site 1 expected approach as (lng, lat) GeoJSON order.
EXPECTED = [[105.32234, -5.41371], [105.3198296, -5.4101864]]
OFF_ROAD = [[105.32234, -5.41371], [105.32300, -5.41400]]  # >30 m from EXPECTED
SLOT = datetime(2026, 10, 13, 3, 0, tzinfo=timezone.utc)


def geojson(coords):
    return json.dumps({"type": "LineString", "coordinates": coords})


def row(route="r1", slot=SLOT, distance=500, actual=EXPECTED, expected_distance=500, expected=EXPECTED):
    return {
        "selected_route_id": route, "slot_time": slot, "demo_distance_m": distance,
        "actual_geojson": geojson(actual) if actual is not None else None,
        "expected_distance_m": expected_distance, "expected_geojson": geojson(expected),
    }


def flags(*rows):
    return [r["demo_rerouted"] for r in bf.flag_rows(rows)]


class FlagRowsTest(unittest.TestCase):
    def test_same_rule_as_live_ingest(self):
        self.assertIs(bf.is_rerouted, is_rerouted)

    def test_keys_and_flag(self):
        out = bf.flag_rows([row()])
        self.assertEqual(out, [{"selected_route_id": "r1", "slot_time": SLOT, "demo_rerouted": False}])

    def test_distance_both_sides(self):
        self.assertEqual(flags(row(distance=551), row(distance=449), row(distance=550), row(distance=450)),
                         [True, True, False, False])

    def test_geometry_outside_buffer(self):
        self.assertEqual(flags(row(actual=OFF_ROAD)), [True])

    def test_null_geometry_falls_back_to_distance(self):
        self.assertEqual(flags(row(actual=None), row(actual=None, distance=700)), [False, True])

    def test_null_distance_uses_geometry(self):
        self.assertEqual(flags(row(distance=None), row(distance=None, actual=OFF_ROAD)), [False, True])

    def test_no_expected_distance_is_false(self):
        self.assertEqual(flags(row(expected_distance=None, distance=900)), [False])


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.flagged = bf.flag_rows([
            row("a", distance=700), row("a", slot=SLOT.replace(minute=30), distance=700),
            row("a", slot=SLOT.replace(hour=4)), row("b", distance=300), row("c"),
        ])

    def test_counts(self):
        n, n_true, n_false, per_route = bf.summarize(self.flagged)
        self.assertEqual((n, n_true, n_false), (5, 3, 2))
        self.assertEqual(dict(per_route), {"a": 2, "b": 1})

    def test_report(self):
        text = bf.report(self.flagged)
        self.assertIn("rows read: 5", text)
        self.assertIn("would set true: 3", text)
        self.assertIn("would set false: 2", text)
        self.assertIn("  a: 2\n  b: 1", text)

    def test_report_no_trues(self):
        self.assertIn("(none)", bf.report(bf.flag_rows([row()])))

    def test_slot_bounds(self):
        lo, hi = bf.slot_bounds(self.flagged)
        self.assertEqual((lo, hi), (SLOT, SLOT.replace(hour=4)))


class MergeSqlTest(unittest.TestCase):
    def setUp(self):
        self.sql = bf.merge_sql("p.d.traffic_snapshots", "p.d._stg")

    def test_keyed_on_route_and_slot_with_pruning(self):
        on = self.sql.split("\nON ")[1].split("\nWHEN MATCHED")[0]
        self.assertIn("T.selected_route_id = S.selected_route_id", on)
        self.assertIn("T.slot_time = S.slot_time", on)
        self.assertIn("T.slot_time BETWEEN @min_slot AND @max_slot", on)

    def test_only_updates_null_flags(self):
        self.assertIn("WHEN MATCHED AND T.demo_rerouted IS NULL THEN UPDATE SET demo_rerouted = S.demo_rerouted",
                      self.sql)

    def test_never_inserts(self):
        self.assertNotIn("NOT MATCHED", self.sql)

    def test_read_sql_selects_only_good_null_rows(self):
        sql = bf.READ_SQL.format(project="p", dataset="d")
        self.assertIn("t.demo_rerouted IS NULL AND t.duration_in_seconds IS NOT NULL", sql)
        self.assertIn("JOIN `p.d.routes` r USING (selected_route_id)", sql)


if __name__ == "__main__":
    unittest.main()
