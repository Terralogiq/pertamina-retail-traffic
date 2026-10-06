"""Unit tests for collector/slots.py and collector/traffic.py (pure functions only).

No network, no key, no google-cloud-bigquery: neither module imports them.
"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "collector"))

import slots  # noqa: E402
import traffic  # noqa: E402

UTC = timezone.utc


def encode_polyline(points):
    """Minimal encoder, only used to build fixtures."""
    out, plat, plng = [], 0, 0
    for lat, lng in points:
        for cur, prev in ((round(lat * 1e5), plat), (round(lng * 1e5), plng)):
            d = cur - prev
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1F)) + 63))
                d >>= 5
            out.append(chr(d + 63))
        plat, plng = round(lat * 1e5), round(lng * 1e5)
    return "".join(out)


def at(h, m, s=0, us=0):
    return datetime(2026, 10, 7, h, m, s, us, tzinfo=UTC)


class SlotTime(unittest.TestCase):
    def test_exact_slots_stay(self):
        self.assertEqual(slots.slot_time(at(12, 0)), at(12, 0))
        self.assertEqual(slots.slot_time(at(12, 30)), at(12, 30))

    def test_start_jitter_rounds_to_nearest(self):
        self.assertEqual(slots.slot_time(at(12, 29, 58)), at(12, 30))
        self.assertEqual(slots.slot_time(at(12, 0, 2)), at(12, 0))
        self.assertEqual(slots.slot_time(at(11, 59, 58)), at(12, 0))
        self.assertEqual(slots.slot_time(at(12, 30, 3)), at(12, 30))

    def test_edge_44_59_rounds_down_to_30(self):
        self.assertEqual(slots.slot_time(at(12, 44, 59)), at(12, 30))
        self.assertEqual(slots.slot_time(at(12, 44, 59, 999999)), at(12, 30))

    def test_edge_45_00_rounds_up_to_next_hour(self):
        self.assertEqual(slots.slot_time(at(12, 45, 0)), at(13, 0))

    def test_edge_14_59_and_15_00(self):
        self.assertEqual(slots.slot_time(at(12, 14, 59)), at(12, 0))
        self.assertEqual(slots.slot_time(at(12, 15, 0)), at(12, 30))

    def test_rolls_over_midnight(self):
        self.assertEqual(slots.slot_time(datetime(2026, 10, 7, 23, 50, tzinfo=UTC)),
                         datetime(2026, 10, 8, 0, 0, tzinfo=UTC))

    def test_other_timezone_is_converted_to_utc(self):
        jakarta = timezone(timedelta(hours=7))
        self.assertEqual(slots.slot_time(datetime(2026, 10, 7, 19, 29, 58, tzinfo=jakarta)), at(12, 30))

    def test_naive_is_taken_as_utc(self):
        self.assertEqual(slots.slot_time(datetime(2026, 10, 7, 12, 29, 58)), at(12, 30))

    def test_iso_is_utc_rfc3339(self):
        self.assertEqual(slots.iso(at(12, 30)), "2026-10-07T12:30:00.000000Z")
        self.assertEqual(slots.iso(datetime(2026, 10, 7, 19, 30, tzinfo=timezone(timedelta(hours=7)))),
                         "2026-10-07T12:30:00.000000Z")
        self.assertIsNone(slots.iso(None))


class DurationAndPolyline(unittest.TestCase):
    def test_parse_duration(self):
        self.assertEqual(traffic.parse_duration_s("123s"), 123.0)
        self.assertEqual(traffic.parse_duration_s("1481s"), 1481.0)
        self.assertEqual(traffic.parse_duration_s("0.5s"), 0.5)
        self.assertIsNone(traffic.parse_duration_s(None))

    def test_decode_polyline_roundtrip(self):
        pts = [(-5.41371, 105.32234), (-5.41019, 105.31983), (-5.40599, 105.31837)]
        self.assertEqual(traffic.decode_polyline(encode_polyline(pts)), pts)

    def test_decode_known_google_example(self):
        # The example from Google's polyline algorithm documentation.
        self.assertEqual(traffic.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@"),
                         [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)])

    def test_wkt_is_lng_lat_order(self):
        wkt = traffic.polyline_to_wkt(encode_polyline([(-5.41371, 105.32234), (-5.41019, 105.31983)]))
        self.assertEqual(wkt, "LINESTRING(105.32234 -5.41371, 105.31983 -5.41019)")

    def test_wkt_drops_repeated_points(self):
        wkt = traffic.polyline_to_wkt(encode_polyline([(1.0, 2.0), (1.0, 2.0), (1.001, 2.001)]))
        self.assertEqual(wkt, "LINESTRING(2.00000 1.00000, 2.00100 1.00100)")

    def test_wkt_none_when_not_a_line(self):
        self.assertIsNone(traffic.polyline_to_wkt(None))
        self.assertIsNone(traffic.polyline_to_wkt(""))
        self.assertIsNone(traffic.polyline_to_wkt(encode_polyline([(1.0, 2.0)])))
        self.assertIsNone(traffic.polyline_to_wkt(encode_polyline([(1.0, 2.0), (1.0, 2.0)])))


def route(leg_index, **kw):
    """A route dict as bq.read_active_routes / main.load_routes_csv return it."""
    points = ((-5.41371, 105.32234, 302, -5.4101864, 105.3198296, 333) if leg_index == 0 else
              (-5.4101864, 105.3198296, 333, -5.4059881, 105.318371, 345))
    base = {
        "selected_route_id": "spbu-2435197-spbuside-" + ("approach", "departure")[leg_index],
        "display_name": "SPBU 24.351.97 · SPBU side · " + ("Approach", "Departure")[leg_index],
        "site_id": "24.351.97", "side": "spbu_side", "call_id": "spbu-2435197-spbuside",
        "leg_index": leg_index, "expected_distance_m": 500,
        **dict(zip(("origin_lat", "origin_lng", "origin_heading", "dest_lat", "dest_lng", "dest_heading"), points)),
    }
    base.update(kw)
    return base


APPROACH_LINE = [(-5.41371, 105.32234), (-5.4101864, 105.3198296)]
DEPARTURE_LINE = [(-5.4101864, 105.3198296), (-5.4059881, 105.318371)]


def response(approach_dur="89s", departure_dur="63s"):
    return {"routes": [{"legs": [
        {"distanceMeters": 500, "duration": approach_dur, "staticDuration": "100s",
         "polyline": {"encodedPolyline": encode_polyline(APPROACH_LINE)}},
        {"distanceMeters": 497, "duration": departure_dur, "staticDuration": "70s",
         "polyline": {"encodedPolyline": encode_polyline(DEPARTURE_LINE)}},
    ]}]}


FETCHED = at(12, 29, 58)
SLOT = slots.slot_time(FETCHED)


class Request(unittest.TestCase):
    def test_group_calls_orders_legs(self):
        calls = traffic.group_calls([route(1), route(0), route(0, call_id="b-call", selected_route_id="x"),
                                     route(1, call_id="b-call", selected_route_id="y")])
        self.assertEqual(list(calls), ["b-call", "spbu-2435197-spbuside"])
        self.assertEqual([r["leg_index"] for r in calls["spbu-2435197-spbuside"]], [0, 1])

    def test_body_runs_entry_front_exit_with_headings(self):
        body = traffic.build_request([route(0), route(1)])
        self.assertEqual(body["origin"], {"location": {
            "latLng": {"latitude": -5.41371, "longitude": 105.32234}, "heading": 302}})
        self.assertEqual(body["intermediates"], [{"location": {
            "latLng": {"latitude": -5.4101864, "longitude": 105.3198296}, "heading": 333}, "via": False}])
        self.assertEqual(body["destination"], {"location": {
            "latLng": {"latitude": -5.4059881, "longitude": 105.318371}, "heading": 345}})
        self.assertEqual(body["travelMode"], "DRIVE")
        self.assertEqual(body["routingPreference"], "TRAFFIC_AWARE")

    def test_front_is_a_stop_not_a_via_point(self):
        stop = traffic.build_request([route(0), route(1)])["intermediates"][0]
        self.assertIs(stop["via"], False)

    def test_missing_heading_is_omitted(self):
        body = traffic.build_request([route(0, origin_heading=None), route(1, dest_heading=None)])
        self.assertNotIn("heading", body["origin"]["location"])
        self.assertNotIn("heading", body["destination"]["location"])
        self.assertEqual(body["intermediates"][0]["location"]["heading"], 333)

    def test_heading_zero_is_kept(self):
        body = traffic.build_request([route(0, origin_heading=0), route(1)])
        self.assertEqual(body["origin"]["location"]["heading"], 0)

    def test_needs_both_legs(self):
        with self.assertRaises(ValueError):
            traffic.build_request([route(0)])
        with self.assertRaises(ValueError):
            traffic.build_request([route(1), route(1)])

    def test_field_mask_asks_only_for_pro_fields(self):
        self.assertEqual(traffic.FIELD_MASK.split(","), [
            "routes.legs.distanceMeters", "routes.legs.duration", "routes.legs.staticDuration",
            "routes.legs.polyline.encodedPolyline"])


class LegRows(unittest.TestCase):
    def rows(self, resp=None, error=None, legs=None):
        legs = legs or [route(0), route(1)]
        request = traffic.build_request(legs)
        return traffic.call_rows(legs, resp if resp is not None else response(), error, SLOT, FETCHED, request)

    def test_core_and_demo_columns(self):
        (r0, r1), error = self.rows()
        self.assertIsNone(error)
        self.assertEqual(r0["selected_route_id"], "spbu-2435197-spbuside-approach")
        self.assertEqual(r0["display_name"], "SPBU 24.351.97 · SPBU side · Approach")
        self.assertEqual(r0["duration_in_seconds"], 89.0)
        self.assertEqual(r0["static_duration_in_seconds"], 100.0)
        self.assertEqual(r0["record_time"], "2026-10-07T12:29:58.000000Z")
        self.assertEqual(r0["fetched_at"], r0["record_time"])
        self.assertEqual(r0["slot_time"], "2026-10-07T12:30:00.000000Z")
        self.assertEqual(r0["road_segment_ids"], [])
        self.assertEqual(r0["speed_reading_intervals"], [])
        self.assertEqual(r0["demo_distance_m"], 500)
        self.assertIsNone(r0["demo_rerouted"])
        self.assertEqual(r0["demo_routing_preference"], "TRAFFIC_AWARE")
        self.assertEqual(r1["selected_route_id"], "spbu-2435197-spbuside-departure")
        self.assertEqual(r1["duration_in_seconds"], 63.0)
        self.assertEqual(r1["demo_distance_m"], 497)

    def test_legs_map_to_their_own_polylines(self):
        (r0, r1), _ = self.rows()
        self.assertTrue(r0["route_geometry"].startswith("LINESTRING(105.32234 -5.41371"))
        self.assertTrue(r1["route_geometry"].startswith("LINESTRING(105.31983 -5.41019"))

    def test_static_ratio_and_speed(self):
        (r0, _), _ = self.rows()
        self.assertAlmostEqual(r0["static_ratio"], 0.89)
        # expected_distance_m / duration * 3.6 = 500 / 89 * 3.6
        self.assertAlmostEqual(r0["speed_kmh"], 500 / 89 * 3.6)
        self.assertAlmostEqual(r0["speed_kmh"], 20.2247, places=3)

    def test_speed_uses_expected_distance_not_returned_distance(self):
        (_, r1), _ = self.rows(legs=[route(0), route(1, expected_distance_m=400)])
        self.assertAlmostEqual(r1["speed_kmh"], 400 / 63 * 3.6)

    def test_speed_none_without_expected_distance_or_duration(self):
        (r0, _), _ = self.rows(legs=[route(0, expected_distance_m=None), route(1)])
        self.assertIsNone(r0["speed_kmh"])
        (r0, _), _ = self.rows(resp=response(approach_dur="0s"))
        self.assertIsNone(r0["speed_kmh"])

    def test_static_ratio_none_when_static_missing_or_zero(self):
        resp = response()
        del resp["routes"][0]["legs"][0]["staticDuration"]
        resp["routes"][0]["legs"][1]["staticDuration"] = "0s"
        (r0, r1), _ = self.rows(resp=resp)
        self.assertIsNone(r0["static_ratio"])
        self.assertIsNone(r0["static_duration_in_seconds"])
        self.assertIsNone(r1["static_ratio"])
        self.assertEqual(r0["duration_in_seconds"], 89.0)

    def test_raw_holds_leg_and_request_but_no_key(self):
        (r0, _), _ = self.rows()
        raw = json.loads(r0["raw"])
        self.assertEqual(raw["leg"]["duration"], "89s")
        self.assertEqual(raw["request"]["intermediates"][0]["via"], False)
        self.assertNotIn("error", raw)
        self.assertNotIn("key", r0["raw"].lower().replace("encodedpolyline", ""))

    def test_failed_call_writes_both_rows_with_null_durations(self):
        (r0, r1), error = self.rows(error="HTTP 403: API key not valid")
        self.assertEqual(error, "HTTP 403: API key not valid")
        for r, rid in ((r0, "approach"), (r1, "departure")):
            self.assertEqual(r["selected_route_id"], "spbu-2435197-spbuside-" + rid)
            self.assertIsNone(r["duration_in_seconds"])
            self.assertIsNone(r["static_duration_in_seconds"])
            self.assertIsNone(r["route_geometry"])
            self.assertIsNone(r["static_ratio"])
            self.assertIsNone(r["speed_kmh"])
            self.assertIsNone(r["demo_distance_m"])
            self.assertEqual(r["slot_time"], "2026-10-07T12:30:00.000000Z")
            self.assertEqual(r["record_time"], "2026-10-07T12:29:58.000000Z")
            raw = json.loads(r["raw"])
            self.assertEqual(raw["error"], "HTTP 403: API key not valid")
            self.assertIn("origin", raw["request"])
            self.assertNotIn("leg", raw)

    def test_response_without_a_route_is_a_failed_call(self):
        (r0, r1), error = self.rows(resp={})
        self.assertEqual(error, "no route in response")
        self.assertIsNone(r0["duration_in_seconds"])
        self.assertEqual(json.loads(r1["raw"])["error"], "no route in response")

    def test_response_with_one_leg_is_a_failed_call(self):
        resp = response()
        del resp["routes"][0]["legs"][1]
        (r0, r1), error = self.rows(resp=resp)
        self.assertEqual(error, "expected 2 legs, got 1")
        self.assertIsNone(r0["duration_in_seconds"])
        self.assertIsNone(r1["duration_in_seconds"])

    def test_rows_are_json_serialisable(self):
        rows, _ = self.rows()
        json.dumps(rows)


class FetchCall(unittest.TestCase):
    def test_never_raises_and_still_returns_both_rows(self):
        # legs 0 only -> build_request raises ValueError inside fetch_call: no network is reached.
        rows, error = traffic.fetch_call("SECRET-KEY", [route(0)], SLOT)
        self.assertIn("ValueError", error)
        self.assertNotIn("SECRET-KEY", error)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["duration_in_seconds"])
        self.assertIn("ValueError", json.loads(rows[0]["raw"])["error"])


if __name__ == "__main__":
    unittest.main()
