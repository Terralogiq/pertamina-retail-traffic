"""TTL cache: entries expire at the next :05/:35 UTC, never later than 30 min."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard.api import cache  # noqa: E402


def at(h, m, s=0):
    return datetime(2026, 10, 7, h, m, s, tzinfo=timezone.utc)


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class NextExpiryTest(unittest.TestCase):
    def test_boundaries(self):
        cases = [
            (at(12, 0), at(12, 5)),
            (at(12, 4, 59), at(12, 5)),
            (at(12, 5), at(12, 35)),      # exactly on a boundary: the next one, 30 min away
            (at(12, 20), at(12, 35)),
            (at(12, 35), at(13, 5)),
            (at(12, 59, 59), at(13, 5)),
            (at(23, 40), at(0, 5) + timedelta(days=1)),
        ]
        for now, want in cases:
            self.assertEqual(cache.next_expiry(now), want, now)

    def test_never_more_than_30_minutes(self):
        now = at(0, 0)
        for _ in range(48 * 60):
            exp = cache.next_expiry(now)
            self.assertGreater(exp, now)
            self.assertLessEqual(exp - now, timedelta(minutes=30))
            now += timedelta(minutes=1)


class TtlCacheTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock(at(12, 10))
        self.cache = cache.TtlCache(clock=self.clock)
        self.calls = 0

    def compute(self):
        self.calls += 1
        return self.calls

    def get(self, endpoint="e", params=None):
        return self.cache.get_or_compute(endpoint, params, self.compute)

    def test_hit_until_boundary_then_recompute(self):
        self.assertEqual(self.get(), 1)
        self.clock.now = at(12, 34, 59)
        self.assertEqual(self.get(), 1)
        self.clock.now = at(12, 35)
        self.assertEqual(self.get(), 2)
        self.clock.now = at(13, 4, 59)
        self.assertEqual(self.get(), 2)
        self.clock.now = at(13, 5)
        self.assertEqual(self.get(), 3)

    def test_keyed_by_endpoint_and_params(self):
        self.assertEqual(self.get("a", {"site": "1", "days": 7}), 1)
        self.assertEqual(self.get("a", {"days": 7, "site": "1"}), 1)  # param order is irrelevant
        self.assertEqual(self.get("a", {"site": "2", "days": 7}), 2)
        self.assertEqual(self.get("b", {"site": "1", "days": 7}), 3)

    def test_clear(self):
        self.get()
        self.cache.clear()
        self.assertEqual(self.get(), 2)


if __name__ == "__main__":
    unittest.main()
