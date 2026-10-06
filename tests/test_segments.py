"""Unit tests for scripts/segments_lib.py and the pure parts of scripts/propose_segments.py.

No network and no API key: importing either module does neither.
"""
import importlib.util
import math
import os
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lib = _load("segments_lib")
ps = _load("propose_segments")

# Site 1 known-good geometry (Jl. P. Tirtayasa, undivided).
PIN_1 = (-5.4103747, 105.3194629)
FRONT_1 = (-5.4101864, 105.3198296)


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


def leg_fixture(distance=500, maneuvers=("DEPART", "NAME_CHANGE"), origin=(0.0, 0.0), dest=None,
                instructions=None, snap=(0.0, 0.0)):
    """A parsed Routes leg running due east from `origin` for `distance` metres."""
    dest = dest or lib.dest_point(origin, 90, distance)
    mid = lib.dest_point(origin, 90, distance / 2)
    steps = []
    for i, m in enumerate(maneuvers):
        ni = {"maneuver": m}
        if instructions:
            ni["instructions"] = instructions[i]
        steps.append({"navigationInstruction": ni})
    return {
        "distanceMeters": distance,
        "duration": "60s", "staticDuration": "70s",
        "startLocation": {"latLng": {"latitude": origin[0] + snap[0], "longitude": origin[1] + snap[1]}},
        "endLocation": {"latLng": {"latitude": dest[0], "longitude": dest[1]}},
        "polyline": {"encodedPolyline": encode_polyline([origin, mid, dest])},
        "steps": steps,
    }, origin, dest, mid


class GeometryTest(unittest.TestCase):
    def test_decode_polyline_google_example(self):
        pts = lib.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        expected = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        self.assertEqual(len(pts), 3)
        for got, want in zip(pts, expected):
            self.assertAlmostEqual(got[0], want[0], places=5)
            self.assertAlmostEqual(got[1], want[1], places=5)

    def test_decode_roundtrips_with_encoder(self):
        pts = [(-5.41, 105.32), (-5.4101, 105.3198), (-6.2925, 106.8117)]
        for got, want in zip(lib.decode_polyline(encode_polyline(pts)), pts):
            self.assertAlmostEqual(got[0], want[0], places=5)
            self.assertAlmostEqual(got[1], want[1], places=5)

    def test_haversine_one_degree_of_latitude(self):
        self.assertAlmostEqual(lib.haversine_m((0, 0), (1, 0)), 111195, delta=5)

    def test_bearing_cardinals(self):
        self.assertAlmostEqual(lib.bearing_deg((0, 0), (1, 0)), 0, places=3)
        self.assertAlmostEqual(lib.bearing_deg((0, 0), (0, 1)), 90, places=3)
        self.assertAlmostEqual(lib.bearing_deg((0, 0), (-1, 0)), 180, places=3)
        self.assertAlmostEqual(lib.bearing_deg((0, 0), (0, -1)), 270, places=3)

    def test_dest_point_roundtrip(self):
        p = (-6.29, 106.81)
        q = lib.dest_point(p, 123, 500)
        self.assertAlmostEqual(lib.haversine_m(p, q), 500, delta=0.01)
        self.assertAlmostEqual(lib.bearing_deg(p, q), 123, delta=0.05)

    def test_angle_diff_wraps(self):
        self.assertEqual(lib.angle_diff(350, 10), 20)
        self.assertEqual(lib.angle_diff(0, 180), 180)

    def test_walk_and_path_length(self):
        a = (0.0, 0.0)
        b = lib.dest_point(a, 90, 300)
        c = lib.dest_point(b, 0, 200)
        path = [a, b, c]
        self.assertAlmostEqual(lib.path_length_m(path), 500, delta=0.1)
        self.assertAlmostEqual(lib.haversine_m(lib.walk(path, 150), a), 150, delta=0.1)
        self.assertAlmostEqual(lib.haversine_m(lib.walk(path, 400), b), 100, delta=0.2)
        self.assertEqual(lib.walk(path, 9999), c)

    def test_nearest_on_path_and_bearing_along(self):
        a = (0.0, 0.0)
        b = lib.dest_point(a, 90, 400)
        side = lib.dest_point(lib.dest_point(a, 90, 250), 0, 30)
        chain, dist, _ = lib.nearest_on_path([a, b], side)
        self.assertAlmostEqual(chain, 250, delta=6)
        self.assertAlmostEqual(dist, 30, delta=1)
        self.assertAlmostEqual(lib.bearing_along([a, b], 200), 90, delta=0.1)


class LeftHandTrafficTest(unittest.TestCase):
    def test_site_1_spbu_side_heading(self):
        # Station is south-west of the road; the road runs 333/153. Left of 333 is 243.
        self.assertTrue(lib.pin_on_left(FRONT_1, 333, PIN_1))
        self.assertFalse(lib.pin_on_left(FRONT_1, 153, PIN_1))
        self.assertEqual(lib.spbu_side_heading(333, FRONT_1, PIN_1), 333)
        self.assertEqual(lib.spbu_side_heading(153, FRONT_1, PIN_1), 333)

    def test_station_on_the_other_side_flips_the_heading(self):
        mirrored = (2 * FRONT_1[0] - PIN_1[0], 2 * FRONT_1[1] - PIN_1[1])
        self.assertEqual(lib.spbu_side_heading(333, FRONT_1, mirrored), 153)

    def test_station_north_of_an_eastbound_road_is_on_the_left(self):
        front = (0.0, 0.0)
        pin = lib.dest_point(front, 0, 40)
        self.assertTrue(lib.pin_on_left(front, 90, pin))
        self.assertFalse(lib.pin_on_left(front, 270, pin))
        self.assertEqual(lib.spbu_side_heading(270, front, pin), 90)


class DirectionsLinkTest(unittest.TestCase):
    URL_1 = ("https://www.google.com/maps/dir/-5.4133268,105.3216993/SPBU+Pertamina+24.351.97/"
             "data=!4m9!4m8!1m0!1m5!1m1!1s0x2e40dc7c04fbeb39:0xf4f0523278473291"
             "!2m2!1d105.3194906!2d-5.4103618!3e0")
    URL_5 = ("https://www.google.com/maps/dir/-6.3658592,107.3554063/SPBU+Rest+Area+KM+57+A/"
             "data=!4m5!4m4!1m0!1m1!1s0x2e697421ff7627c7:0x54da4a415990ed91!3e0")
    EXIT_3 = ("https://www.google.com/maps/dir/SPBU+34-12103+Lingkar+Selatan,+Jl.+TB+Simatupang+No.20+2/"
              "-6.2926601,106.8073713/@-6.2929164,106.8073227,18.99z/data=!4m9!4m8!1m5!1m1"
              "!1s0x2e69f1f962b88bfd:0x156adf506542af4a!2m2!1d106.8117191!2d-6.2925025!1m0!3e0")

    def test_fid_to_place_id_known_sites(self):
        self.assertEqual(lib.fid_to_place_id("0x2e40dc7c04fbeb39", "0xf4f0523278473291"),
                         "ChIJOev7BHzcQC4RkTJHeDJS8PQ")
        self.assertEqual(lib.fid_to_place_id("0x2e697421ff7627c7", "0x54da4a415990ed91"),
                         "ChIJxyd2_yF0aS4Rke2QWUFK2lQ")

    def test_parse_directions_url(self):
        self.assertEqual(lib.parse_directions_url(self.URL_1),
                         ((-5.4133268, 105.3216993), "ChIJOev7BHzcQC4RkTJHeDJS8PQ"))
        self.assertEqual(lib.parse_directions_url(self.URL_5),
                         ((-6.3658592, 107.3554063), "ChIJxyd2_yF0aS4Rke2QWUFK2lQ"))

    def test_parse_directions_destination(self):
        self.assertEqual(lib.parse_directions_destination(self.EXIT_3), (-6.2926601, 106.8073713))
        self.assertEqual(lib.parse_directions_destination(
            "https://www.google.com/maps/dir/SPBU/-6.2926601,106.8073713/data=!4m5!4m4!1m1!1s0x1:0x2!1m0!3e0"),
            (-6.2926601, 106.8073713))

    def test_destination_rejects_an_entry_link(self):
        with self.assertRaises(ValueError):
            lib.parse_directions_destination(self.URL_1)

    def test_parse_rejects_other_links(self):
        with self.assertRaises(ValueError):
            lib.parse_directions_url("https://maps.app.goo.gl/uswuDgiNCqMQsjYW9")


class RoadNameTest(unittest.TestCase):
    def test_same_road_written_differently(self):
        for wanted, seen in (("Jl. P. Tirtayasa", "Jalan P. Tirtayasa"),
                             ("Jl. By Pass Ngurah Rai", "Jl. Bypass Ngurah Rai"),
                             ("Jl. MT Haryono", "Jl. Letjen MT Haryono"),
                             ("Jl. Dr. Djunjunan", "Jl. Dr. Djunjunan"),
                             ("Jl. Daan Mogot", "Jl. Daan Mogot/Jl. Pantura")):
            with self.subTest(wanted=wanted, seen=seen):
                self.assertTrue(lib.road_matches(wanted, seen))

    def test_different_roads_do_not_match(self):
        self.assertFalse(lib.road_matches("Jl. TB Simatupang", "Jl. Tol Lkr. Luar Jkt/Jl. Tol Tahi Bonar Simatupang"))
        self.assertFalse(lib.road_matches("Jl. Ahmad Yani", "Jl. Gayung Kebonsari"))
        self.assertFalse(lib.road_matches("", "Jl. Ahmad Yani"))

    def test_road_of_instruction(self):
        self.assertEqual(lib.road_of_instruction("Turn left onto Jl. Dr. Djunjunan\nPass by Police (on the left)"),
                         "Jl. Dr. Djunjunan")
        self.assertEqual(lib.road_of_instruction("Head west on Jl. TB Simatupang toward Jl. Jeruk Purut"),
                         "Jl. TB Simatupang")
        self.assertEqual(lib.road_of_instruction("Turn right toward Jl. Ahmad Yani"), "")
        self.assertEqual(lib.road_of_instruction("Make a U-turn"), "")
        self.assertEqual(lib.road_of_instruction(None), "")


class ParsingTest(unittest.TestCase):
    def test_parse_duration(self):
        self.assertEqual(lib.parse_duration_s("1481s"), 1481.0)
        self.assertEqual(lib.parse_duration_s("67.5s"), 67.5)
        self.assertIsNone(lib.parse_duration_s(None))

    def test_leg_maneuvers_skip_depart(self):
        leg = {"steps": [{"navigationInstruction": {"maneuver": "DEPART"}},
                         {"navigationInstruction": {}},
                         {"navigationInstruction": {"maneuver": "TURN_LEFT"}}, {}]}
        self.assertEqual(lib.leg_maneuvers(leg), ["TURN_LEFT"])

    def test_leg_roads_and_toll(self):
        leg = {"steps": [
            {"navigationInstruction": {"instructions": "Head west on Jl. A\nToll road"}},
            {"navigationInstruction": {"instructions": "Continue onto Jl. B"}},
            {"navigationInstruction": {"instructions": "Continue onto Jl. B"}}]}
        self.assertEqual(lib.leg_roads(leg), ["Jl. A", "Jl. B"])
        self.assertTrue(lib.leg_on_toll(leg))
        self.assertFalse(lib.leg_on_toll({"steps": [{"navigationInstruction": {"instructions": "Head west on Jl. A"}}]}))


class ValidateLegTest(unittest.TestCase):
    def test_clean_500m_leg_passes(self):
        leg, o, d, mid = leg_fixture()
        self.assertEqual(lib.validate_leg(leg, o, d, mid), (True, []))

    def test_name_change_and_straight_are_fine(self):
        leg, o, d, mid = leg_fixture(maneuvers=("DEPART", "NAME_CHANGE", "STRAIGHT"))
        self.assertTrue(lib.validate_leg(leg, o, d, mid)[0])

    def test_ramp_fails(self):
        leg, o, d, mid = leg_fixture(maneuvers=("DEPART", "RAMP_LEFT"))
        ok, why = lib.validate_leg(leg, o, d, mid)
        self.assertFalse(ok)
        self.assertTrue(any("RAMP_LEFT" in w for w in why))

    def test_uturn_and_turn_fail(self):
        for man in ("UTURN_RIGHT", "TURN_LEFT", "TURN_SLIGHT_RIGHT"):
            with self.subTest(man=man):
                leg, o, d, mid = leg_fixture(maneuvers=("DEPART", man))
                self.assertFalse(lib.validate_leg(leg, o, d, mid)[0])

    def test_detour_over_1_15_of_straight_line_fails(self):
        leg, o, d, mid = leg_fixture(distance=500)
        leg["distanceMeters"] = 700          # still inside 400-700 m, but 1.4x the 500 m chord
        ok, why = lib.validate_leg(leg, o, d, mid)
        self.assertFalse(ok)
        self.assertTrue(any("1.40x" in w for w in why))

    def test_short_leg_fails_but_passes_a_300m_limit(self):
        leg, o, d, mid = leg_fixture(distance=350)
        ok, why = lib.validate_leg(leg, o, d, mid)
        self.assertFalse(ok)
        self.assertTrue(any("outside 400-700" in w for w in why))
        self.assertTrue(lib.validate_leg(leg, o, d, mid, limits=(300, 700))[0])

    def test_long_leg_fails(self):
        leg, o, d, mid = leg_fixture(distance=800)
        self.assertFalse(lib.validate_leg(leg, o, d, mid)[0])

    def test_toll_limits(self):
        leg, o, d, mid = leg_fixture(distance=1000)
        self.assertFalse(lib.validate_leg(leg, o, d, mid)[0])
        self.assertTrue(lib.validate_leg(leg, o, d, mid, limits=lib.TOLL_LIMITS_M)[0])
        leg, o, d, mid = leg_fixture(distance=1400)
        self.assertFalse(lib.validate_leg(leg, o, d, mid, limits=lib.TOLL_LIMITS_M)[0])

    def test_start_snapped_far_from_request_fails(self):
        leg, o, d, mid = leg_fixture(snap=(0.0, 0.0005))      # about 55 m
        ok, why = lib.validate_leg(leg, o, d, mid)
        self.assertFalse(ok)
        self.assertTrue(any("start snapped" in w for w in why))

    def test_polyline_missing_front_fails(self):
        leg, o, d, mid = leg_fixture()
        far_front = lib.dest_point(mid, 0, 80)
        ok, why = lib.validate_leg(leg, o, d, far_front)
        self.assertFalse(ok)
        self.assertTrue(any("misses Front" in w for w in why))

    def test_toll_road_leg_fails_unless_allowed(self):
        leg, o, d, mid = leg_fixture(maneuvers=("DEPART",), instructions=("Head east on Jl. A\nToll road",))
        ok, why = lib.validate_leg(leg, o, d, mid)
        self.assertFalse(ok)
        self.assertTrue(any("toll road" in w for w in why))
        self.assertTrue(lib.validate_leg(leg, o, d, mid, allow_toll=True)[0])

    def test_missing_distance_fails(self):
        self.assertEqual(lib.validate_leg({}, (0, 0), (0, 0.004), (0, 0.002)), (False, ["no distance"]))


class ProposeSegmentsPureTest(unittest.TestCase):
    SITE = {"site_no": "1", "spbu_code": "24.351.97"}

    def test_route_id_strips_dots_and_names_sides(self):
        self.assertEqual(ps.route_id(self.SITE, "spbu_side", "approach"), "spbu-2435197-spbuside-approach")
        self.assertEqual(ps.route_id(self.SITE, "opposite", "departure"), "spbu-2435197-opposite-departure")
        self.assertEqual(ps.route_id({"spbu_code": "KM57A"}, "spbu_side", "departure"),
                         "spbu-KM57A-spbuside-departure")

    def test_csv_point_rounds_like_the_csv(self):
        self.assertEqual(ps.csv_point(((-5.410186412345, 105.31982961234), 332.6)),
                         ((-5.4101864, 105.3198296), 333))
        self.assertEqual(ps.csv_point(((0.0, 0.0), 359.7))[1], 0)

    def test_side_rows_ok(self):
        pts = [((-5.41371, 105.32234), 302), ((-5.4101864, 105.3198296), 333), ((-5.4059881, 105.318371), 345)]
        legs = [{"distance_m": 500, "polyline": "abc"}, {"distance_m": 499, "polyline": "def"}]
        rows = ps.side_rows(self.SITE, "spbu_side", {"status": "ok", "pts": pts, "legs": legs, "note": "n"})
        self.assertEqual([r["leg"] for r in rows], ["approach", "departure"])
        self.assertEqual([r["leg_index"] for r in rows], [0, 1])
        self.assertEqual({r["call_id"] for r in rows}, {"spbu-2435197-spbuside"})
        self.assertEqual((rows[0]["origin_lat"], rows[0]["origin_heading"], rows[0]["dest_heading"]),
                         ("-5.4137100", 302, 333))
        self.assertEqual((rows[1]["origin_lat"], rows[1]["dest_lng"], rows[1]["dest_heading"]),
                         ("-5.4101864", "105.3183710", 345))
        self.assertEqual([r["expected_distance_m"] for r in rows], [500, 499])
        self.assertEqual([r["expected_polyline"] for r in rows], ["abc", "def"])
        self.assertEqual(list(rows[0]), ps.ROUTES_COLUMNS)

    def test_side_rows_needs_link_without_points(self):
        rows = ps.side_rows(self.SITE, "opposite", {"status": "needs_link", "note": "no step onto the named road"})
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["status"] == "needs_link" and r["origin_lat"] == "" and r["expected_polyline"] == ""
                            for r in rows))
        self.assertEqual(rows[0]["selected_route_id"], "spbu-2435197-opposite-approach")

    def test_clean_stretch_stops_at_the_first_turn(self):
        def step(man, a, b):
            return {"navigationInstruction": {"maneuver": man}, "polyline": {"encodedPolyline": encode_polyline([a, b])}}
        p0 = (0.0, 0.0)
        p1 = lib.dest_point(p0, 90, 300)
        p2 = lib.dest_point(p1, 90, 200)
        p3 = lib.dest_point(p2, 0, 100)
        pts, blocked = ps.clean_stretch([step("DEPART", p0, p1), step("NAME_CHANGE", p1, p2), step("TURN_LEFT", p2, p3)])
        self.assertEqual(blocked, "TURN_LEFT")
        self.assertAlmostEqual(lib.path_length_m(pts), 500, delta=1)
        pts, blocked = ps.clean_stretch([step("DEPART", p0, p1), step("RAMP_LEFT", p1, p2)])
        self.assertEqual(blocked, "RAMP_LEFT")


class FakeMaps:
    """Stands in for propose_segments.Maps: a perfectly straight road, no network."""

    def __init__(self, turn_after_m=None, always=False, place_dest=None, turn_leg=None):
        self.calls = []
        self.place_dest = place_dest   # where a route to a placeId ends
        self.turn_leg = turn_leg       # traffic(): leg index (0/1) that gets a TURN_LEFT step
        self.turn_after_m = turn_after_m
        self.always = always         # turn every time, not just on the first probe

    def probe(self, origin, dest, **extra):
        o = (origin["location"]["latLng"]["latitude"], origin["location"]["latLng"]["longitude"])
        d = self.place_dest if "placeId" in dest else (
            dest["location"]["latLng"]["latitude"], dest["location"]["latLng"]["longitude"])
        self.calls.append((o, d))
        turns = self.turn_after_m and (self.always or len(self.calls) == 1)
        mid = lib.walk([o, d], self.turn_after_m) if turns else d
        steps = [{"navigationInstruction": {"maneuver": "DEPART", "instructions": "Head east on Jl. Test"},
                  "distanceMeters": int(lib.haversine_m(o, mid)),
                  "polyline": {"encodedPolyline": encode_polyline([o, mid])}}]
        if turns:
            side = lib.dest_point(mid, 0, 100)
            steps.append({"navigationInstruction": {"maneuver": "TURN_LEFT"},
                          "polyline": {"encodedPolyline": encode_polyline([mid, side])}})
        return {"routes": [{"legs": [{"steps": steps}]}]}

    def traffic(self, origin, stop, dest):
        def at(w):
            return (w["location"]["latLng"]["latitude"], w["location"]["latLng"]["longitude"])
        pts = [at(origin), at(stop), at(dest)]
        legs = []
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            steps = [{"navigationInstruction": {"maneuver": "DEPART", "instructions": "Head east on Jl. Test"}}]
            if i == self.turn_leg:
                steps.append({"navigationInstruction": {"maneuver": "TURN_LEFT", "instructions": "Turn left"}})
            legs.append({"distanceMeters": int(round(lib.haversine_m(a, b))), "duration": "60s", "staticDuration": "50s",
                         "startLocation": {"latLng": {"latitude": a[0], "longitude": a[1]}},
                         "endLocation": {"latLng": {"latitude": b[0], "longitude": b[1]}},
                         "polyline": {"encodedPolyline": encode_polyline([a, b])}, "steps": steps})
        return {"routes": [{"legs": legs}]}


class TraceTest(unittest.TestCase):
    def test_trace_extends_until_it_has_enough_road(self):
        maps = FakeMaps()
        path, blocked = ps.trace(maps, (0.0, 0.0), 90, 2500)
        self.assertIsNone(blocked)
        self.assertGreaterEqual(lib.path_length_m(path), 2500)
        self.assertGreater(len(maps.calls), 1)       # each probe reaches at most 1,000 m

    def test_trace_restarts_from_the_end_of_a_clean_stretch(self):
        maps = FakeMaps(turn_after_m=400)           # first probe turns off at 400 m, later ones don't
        path, blocked = ps.trace(maps, (0.0, 0.0), 90, 1000)
        self.assertIsNone(blocked)
        self.assertGreaterEqual(lib.path_length_m(path), 1000)
        self.assertEqual(len(maps.calls), 2)

    def test_trace_reports_a_road_it_cannot_follow(self):
        path, blocked = ps.trace(FakeMaps(turn_after_m=10, always=True), (0.0, 0.0), 90, 1000)
        self.assertEqual(blocked, "TURN_LEFT")
        self.assertEqual(path, [])

    def test_link_for_the_wrong_place_is_rejected_before_any_call(self):
        with self.assertRaises(ValueError):
            ps.link_anchor(None, DirectionsLinkTest.URL_1, {"site_no": "2", "place_id": "ChIJother"})


class LinkOverrideTest(unittest.TestCase):
    """derive_site on a straight east-west road with the SPBU 40 m north of it (left of eastbound)."""
    FID = "0x2e69f1f962b88bfd:0x156adf506542af4a"
    PLACE_ID = lib.fid_to_place_id(*FID.split(":"))
    ENTRY = (0.0, 0.0)
    ON_ROAD = lib.dest_point(ENTRY, 90, 500)
    PIN = lib.dest_point(ON_ROAD, 0, 40)
    EXIT = lib.dest_point(ON_ROAD, 90, 483)
    ENTRY_URL = f"https://www.google.com/maps/dir/0.0,0.0/SPBU/data=!4m5!4m4!1m0!1m1!1s{FID}!3e0"
    EXIT_URL = (f"https://www.google.com/maps/dir/SPBU/{EXIT[0]:.7f},{EXIT[1]:.7f}/"
                f"data=!4m5!4m4!1m1!1s{FID}!1m0!3e0")

    def derive(self, site_no, exit_url, turn_leg):
        site = {"site_no": site_no, "place_id": self.PLACE_ID}
        maps = FakeMaps(place_dest=self.ON_ROAD, turn_leg=turn_leg)
        link = ("spbu_side", self.ENTRY_URL, exit_url)
        return ps.derive_site(maps, site, self.PIN, ["Jl. Test"], link, False)["spbu_side"]

    def test_exit_url_sets_the_exit_and_the_listed_site_accepts_its_turn_left(self):
        self.assertIn("3", ps.LINK_ENTRY_SITES)
        res = self.derive("3", self.EXIT_URL, turn_leg=1)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["attempts"], 1)
        self.assertEqual(res["pts"][2][0], (round(self.EXIT[0], 7), round(self.EXIT[1], 7)))
        self.assertEqual(res["pts"][0][0], self.ENTRY)           # the link's own Entry is kept
        self.assertEqual(res["legs"][1]["maneuvers"], ["TURN_LEFT"])

    def test_turn_left_is_rejected_for_a_site_without_the_override(self):
        self.assertNotIn("9", ps.LINK_ENTRY_SITES)
        res = self.derive("9", self.EXIT_URL, turn_leg=1)
        self.assertEqual(res["status"], "needs_link")
        self.assertIn("departure: maneuvers TURN_LEFT", res["note"])

    def test_the_accepted_turn_is_for_the_departure_only(self):
        res = self.derive("3", self.EXIT_URL, turn_leg=0)
        self.assertEqual(res["status"], "needs_link")
        self.assertIn("approach: maneuvers TURN_LEFT", res["note"])

    def test_exit_url_sets_the_exit_for_a_site_without_the_override(self):
        res = self.derive("9", self.EXIT_URL, turn_leg=None)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["pts"][2][0], (round(self.EXIT[0], 7), round(self.EXIT[1], 7)))

    def test_sides_for_is_the_spbu_side_only(self):
        for toll in (False, True):
            self.assertEqual(tuple(ps.sides_for({"site_no": "1"}, toll)), ("spbu_side",))


class KeepOnRoadTest(unittest.TestCase):
    def step(self, maneuver, text):
        return {"navigationInstruction": {"maneuver": maneuver, "instructions": text}}

    def test_keep_left_continue_is_not_a_turn(self):
        leg = {"steps": [self.step("DEPART", "Head west on Jl. TB Simatupang"),
                         self.step("TURN_LEFT", "Keep left to continue on Jl. TB Simatupang\nDestination will be on the left")]}
        self.assertEqual(lib.leg_maneuvers(leg, ["Jl. TB Simatupang"]), [])

    def test_without_road_names_nothing_is_dropped(self):
        leg = {"steps": [self.step("TURN_LEFT", "Keep left to continue on Jl. TB Simatupang")]}
        self.assertEqual(lib.leg_maneuvers(leg), ["TURN_LEFT"])

    def test_keep_left_onto_a_different_road_still_counts(self):
        leg = {"steps": [self.step("TURN_LEFT", "Keep left to continue on Jl. Tol Pondok Pinang")]}
        self.assertEqual(lib.leg_maneuvers(leg, ["Jl. TB Simatupang"]), ["TURN_LEFT"])

    def test_real_turn_still_counts(self):
        leg = {"steps": [self.step("TURN_LEFT", "Turn left"),
                         self.step("TURN_RIGHT", "Keep right onto the ramp")]}
        self.assertEqual(lib.leg_maneuvers(leg, ["Jl. TB Simatupang"]), ["TURN_LEFT", "TURN_RIGHT"])


class AcceptedManeuverTest(unittest.TestCase):
    def test_user_verified_label_is_accepted_only_when_listed(self):
        leg = {"distanceMeters": 483, "steps": [
            {"navigationInstruction": {"maneuver": "DEPART", "instructions": "Head west"}},
            {"navigationInstruction": {"maneuver": "TURN_LEFT", "instructions": "Turn left"}}]}
        o, d = (-6.2923962, 106.8117085), (-6.2926601, 106.8073713)
        ok, why = lib.validate_leg(leg, o, d, o)
        self.assertTrue(any("TURN_LEFT" in w for w in why))
        ok, why = lib.validate_leg(leg, o, d, o, accepted=("TURN_LEFT",))
        self.assertFalse(any("TURN_LEFT" in w for w in why))


if __name__ == "__main__":
    unittest.main()
