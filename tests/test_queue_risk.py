"""Queue-risk tier and sort order (dashboard/api/queue_risk.py) on the 2026-10-14 Results table."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.api import queue_risk  # noqa: E402

# docs/plans/queue-risk.md "Results": 2026-10-06 17:30 to 2026-10-14 08:30 UTC, 7 full days per site.
# (als_pct, both_slow_pct, departure_only_pct, days_with_2h_als, als_median_delay_s)
RESULTS = {
    "54.801.17": (29.8, 10.7, 2.2, 7, 75),   # Pemogan
    "61.761.03": (25.7, 11.2, 2.2, 7, 30),   # MT Haryono
    "74.902.22": (26.2, 32.8, 0.3, 7, 28),   # Makassar
    "34.121.03": (19.7, 3.0, 0.0, 6, 25),    # Lingkar Selatan
    "24.351.97": (6.0, 3.6, 10.7, 3, 36),    # Tirtayasa
    "24.351.34": (6.0, 8.2, 16.1, 3, 26),    # Antasari
    "KM57A": (3.3, 0.0, 0.3, 2, 77),
    "54.601.80": (0.3, 0.0, 0.8, 0, 42),     # Gayungan
    "34.117.12": (1.9, 22.4, 16.9, 0, 30),   # Daan Mogot
    "34.401.16": (0.0, 33.6, 27.3, 0, None),  # Bandung
}


def metrics(als, both, departure, days, median, full_days=7):
    return {"als_pct": als, "both_slow_pct": both, "departure_only_pct": departure,
            "days_with_2h_als": days, "full_days": full_days, "als_median_delay_s": median}


def fixture():
    return [{"site_id": site, **metrics(*values)} for site, values in RESULTS.items()]


class TierTest(unittest.TestCase):
    def test_results_table_tiers(self):
        tiers = {e["site_id"]: queue_risk.tier(e) for e in fixture()}
        self.assertEqual(tiers, {
            "54.801.17": "strong",
            "61.761.03": "moderate", "74.902.22": "moderate", "34.121.03": "moderate",
            "24.351.97": "weak", "24.351.34": "weak", "KM57A": "weak",
            "54.601.80": "none",
            "34.117.12": "cannot_tell", "34.401.16": "cannot_tell",
        })

    def test_results_table_sort_order(self):
        entries = [{**e, "tier": queue_risk.tier(e)} for e in fixture()]
        entries.reverse()  # input order must not matter
        ordered = [e["site_id"] for e in sorted(entries, key=queue_risk.sort_key)]
        self.assertEqual(ordered, [
            "54.801.17", "61.761.03", "74.902.22", "34.121.03",
            "24.351.97", "24.351.34", "KM57A", "54.601.80", "34.117.12", "34.401.16"])

    def test_all_zero_site_is_none(self):
        self.assertEqual(queue_risk.tier(metrics(0.0, 0.0, 0.0, 0, None)), "none")

    def test_no_full_day_is_never_strong_or_moderate(self):
        self.assertEqual(queue_risk.tier(metrics(5.0, 0.0, 0.0, 0, 90, full_days=0)), "none")
        self.assertEqual(queue_risk.tier(metrics(0.0, 0.0, 0.0, 0, None, full_days=0)), "none")

    def test_null_median_cannot_be_strong(self):
        self.assertEqual(queue_risk.tier(metrics(20.0, 0.0, 0.0, 7, None)), "moderate")

    def test_strong_needs_a_minute(self):
        self.assertEqual(queue_risk.tier(metrics(20.0, 0.0, 0.0, 7, 60)), "strong")
        self.assertEqual(queue_risk.tier(metrics(20.0, 0.0, 0.0, 7, 59.9)), "moderate")

    def test_recurrence_bar_is_seventy_percent_of_full_days(self):
        self.assertEqual(queue_risk.tier(metrics(10.0, 0.0, 0.0, 5, 30)), "moderate")  # 5 >= 4.9
        self.assertEqual(queue_risk.tier(metrics(10.0, 0.0, 0.0, 4, 30)), "weak")      # 4 < 4.9
        self.assertEqual(queue_risk.tier(metrics(10.0, 0.0, 0.0, 1, 30)), "weak")

    def test_cannot_tell_is_strict_and_needs_both_conditions(self):
        self.assertEqual(queue_risk.tier(metrics(5.0, 10.0, 10.0, 7, 90)), "strong")  # exactly 2x: not masked
        self.assertEqual(queue_risk.tier(metrics(5.0, 10.01, 10.01, 0, None)), "cannot_tell")
        self.assertEqual(queue_risk.tier(metrics(5.0, 20.0, 10.0, 0, None)), "none")  # departure-only equals 2x
        self.assertEqual(queue_risk.tier(metrics(5.0, 10.0, 20.0, 0, None)), "none")  # both-slow equals 2x

    def test_cannot_tell_wins_over_recurrence(self):
        self.assertEqual(queue_risk.tier(metrics(5.0, 12.0, 12.0, 7, 90)), "cannot_tell")


class SortKeyTest(unittest.TestCase):
    def entry(self, site_id, tier, days, median):
        return {"site_id": site_id, "tier": tier, "days_with_2h_als": days, "als_median_delay_s": median}

    def order(self, entries):
        return [e["site_id"] for e in sorted(entries, key=queue_risk.sort_key)]

    def test_tier_then_days_then_median_then_site_id(self):
        entries = [
            self.entry("e", "moderate", 6, 90), self.entry("d", "moderate", 7, 20),
            self.entry("c", "moderate", 7, 40), self.entry("b", "moderate", 7, None),
            self.entry("a", "moderate", 7, 40), self.entry("s", "strong", 1, 60),
            self.entry("z", "cannot_tell", 7, 90), self.entry("n", "none", 0, None),
        ]
        self.assertEqual(self.order(entries), ["s", "a", "c", "d", "b", "e", "n", "z"])


class ConfidenceFileTest(unittest.TestCase):
    def test_every_fixture_site_has_a_dated_entry(self):
        confidence = queue_risk.load_confidence()
        self.assertEqual(set(confidence), set(RESULTS))
        for site, entry in confidence.items():
            with self.subTest(site=site):
                self.assertEqual(set(entry), {"level", "reason", "as_of"})
                self.assertIn(entry["level"], {"medium", "low", "very_low", "none"})
                self.assertRegex(entry["as_of"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(entry["reason"])

    def test_reasons_never_say_queue(self):
        # "Likely queue" wording stays hidden until validation steps 3 or 4 confirm (docs/plans/queue-risk.md)
        for site, entry in queue_risk.load_confidence().items():
            with self.subTest(site=site):
                self.assertNotIn("queue", entry["reason"].lower())

    def test_levels_match_the_ranking_table(self):
        levels = {site: entry["level"] for site, entry in queue_risk.load_confidence().items()}
        self.assertEqual(levels, {
            "54.801.17": "medium", "61.761.03": "low", "74.902.22": "low", "34.121.03": "low",
            "24.351.97": "very_low", "24.351.34": "very_low", "KM57A": "very_low",
            "54.601.80": "medium", "34.117.12": "none", "34.401.16": "none"})


if __name__ == "__main__":
    unittest.main()
