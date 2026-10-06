"""Unit tests for the pure helpers in scripts/places_test_fetch.py.

Importing the module makes no network calls and does not fetch the API key:
both happen only inside main().
"""
import importlib.util
import json
import os
import tempfile
import unittest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "places_test_fetch.py")
_spec = importlib.util.spec_from_file_location("places_test_fetch", SCRIPT)
ptf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ptf)


class BrandOfTest(unittest.TestCase):
    def test_pertamina_code_variants(self):
        for name in ("24.351-34", "3440116", "54.601.80", "24-351-34"):
            with self.subTest(name=name):
                self.assertEqual(ptf.brand_of(name), "Pertamina")

    def test_pertamina_by_name(self):
        self.assertEqual(ptf.brand_of("SPBU Pertamina - Tirtayasa"), "Pertamina")
        self.assertEqual(ptf.brand_of("Pertamax Turbo Kiosk"), "Pertamina")

    def test_pertamini_is_other(self):
        self.assertEqual(ptf.brand_of("Pertamini Pak Joko"), "other")

    def test_shell(self):
        self.assertEqual(ptf.brand_of("Shell Jl. Sudirman"), "Shell")

    def test_bp(self):
        self.assertEqual(ptf.brand_of("bp Pangeran Antasari"), "BP")
        self.assertEqual(ptf.brand_of("BP-AKR Kemang"), "BP")

    def test_vivo(self):
        self.assertEqual(ptf.brand_of("SPBU VIVO Pasteur"), "Vivo")

    def test_missing_or_unrelated_is_other(self):
        for name in (None, "", "Indomaret Point"):
            with self.subTest(name=name):
                self.assertEqual(ptf.brand_of(name), "other")

    def test_short_digit_runs_are_not_codes(self):
        self.assertEqual(ptf.brand_of("Toko 12345"), "other")


class NonEmptyTest(unittest.TestCase):
    def test_present_values(self):
        for v in (False, True, 0, 0.0, "x", [0], {"a": 1}):
            with self.subTest(v=v):
                self.assertTrue(ptf.non_empty(v))

    def test_missing_values(self):
        for v in (None, "", [], {}):
            with self.subTest(v=v):
                self.assertFalse(ptf.non_empty(v))


class RoadTest(unittest.TestCase):
    def test_norm_road_strips_prefix_and_honorifics(self):
        self.assertEqual(ptf.norm_road("Jl. P. Antasari"), "antasari")
        self.assertEqual(ptf.norm_road("Jalan Pangeran Antasari"), "antasari")
        self.assertEqual(ptf.norm_road("Jl. Dr. Setiabudi"), "setiabudi")

    def test_abbreviation_matches_full_form(self):
        self.assertTrue(
            ptf.road_matches("Jl. P. Antasari", "Jalan Pangeran Antasari"))

    def test_case_and_punctuation_insensitive(self):
        self.assertTrue(ptf.road_matches("JL. TIRTAYASA", "jalan tirtayasa"))

    def test_partial_token_overlap_meets_threshold(self):
        # 1 of min(2, 3) tokens shared = 0.5, the threshold is inclusive
        self.assertTrue(ptf.road_matches("Jl. Raya Bogor", "Jalan Bogor Lama Baru"))

    def test_different_roads_do_not_match(self):
        self.assertFalse(ptf.road_matches("Jl. Sudirman", "Jalan Thamrin"))

    def test_empty_route_is_false(self):
        self.assertFalse(ptf.road_matches("Jl. Sudirman", ""))

    def test_route_of_missing_route_component(self):
        # build_report maps this "" to road_match=None
        self.assertEqual(ptf.route_of({}), "")
        self.assertEqual(
            ptf.route_of({"addressComponents": [
                {"types": ["locality"], "longText": "Bandung"}]}), "")

    def test_route_of_prefers_long_text(self):
        d = {"addressComponents": [
            {"types": ["route"], "longText": "Jalan Pasteur", "shortText": "Jl. Pasteur"}]}
        self.assertEqual(ptf.route_of(d), "Jalan Pasteur")


class NearbyStatsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _write(self, payload, name="nearby.json"):
        path = os.path.join(self._tmp.name, name)
        with open(path, "w") as f:
            json.dump(payload, f)
        return path

    @staticmethod
    def _place(pid, name):
        return {"id": pid, "displayName": {"text": name}}

    def test_missing_file_is_none(self):
        self.assertIsNone(
            ptf.nearby_stats(os.path.join(self._tmp.name, "nope.json"), "S"))

    def test_error_payload_is_none(self):
        self.assertIsNone(ptf.nearby_stats(self._write({"_error": {}, "_status": 403}), "S"))

    def test_empty_response(self):
        counts, total, capped = ptf.nearby_stats(self._write({}), "S")
        self.assertEqual(total, 0)
        self.assertFalse(capped)
        self.assertEqual(counts, {b: 0 for b in ptf.BRANDS})

    def test_counts_by_brand_and_excludes_self(self):
        path = self._write({"places": [
            self._place("S", "SPBU Pertamina 24.351-34"),  # the site itself
            self._place("A", "SPBU Pertamina 3440116"),
            self._place("B", "Shell Pasteur"),
            self._place("C", "bp Pangeran Antasari"),
            self._place("D", "SPBU VIVO Pasteur"),
            self._place("E", "Pertamini Pak Joko"),
            {"id": "F"},  # no displayName
        ]})
        counts, total, capped = ptf.nearby_stats(path, "S")
        self.assertEqual(counts, {"Pertamina": 1, "Shell": 1, "BP": 1, "Vivo": 1, "other": 2})
        self.assertEqual(total, 6)
        self.assertFalse(capped)

    def test_cap_flagged_at_20_and_self_excluded_from_count(self):
        places = [self._place("S", "SPBU Pertamina 24.351-34")]
        places += [self._place(f"P{i}", "Shell") for i in range(19)]
        counts, total, capped = ptf.nearby_stats(self._write({"places": places}), "S")
        self.assertTrue(capped)  # 20 returned by the API, including the site
        self.assertEqual(total, 19)
        self.assertEqual(counts["Shell"], 19)
        self.assertEqual(counts["Pertamina"], 0)

    def test_19_results_not_capped(self):
        places = [self._place(f"P{i}", "Shell") for i in range(19)]
        _, total, capped = ptf.nearby_stats(self._write({"places": places}), "S")
        self.assertFalse(capped)
        self.assertEqual(total, 19)


class ImportSafetyTest(unittest.TestCase):
    def test_key_and_network_only_in_main(self):
        # Import above already succeeded without gcloud/env/network; the
        # entry point must stay behind the __main__ guard.
        self.assertTrue(callable(ptf.main))
        self.assertEqual(ptf.CALLS["details"], 0)


if __name__ == "__main__":
    unittest.main()
