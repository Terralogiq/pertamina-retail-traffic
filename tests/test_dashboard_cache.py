"""TTL cache: entries expire at the next :05/:35 UTC, never later than 30 min."""
import os
import sys
import threading
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

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

    def test_expired_entries_are_dropped_on_store(self):
        self.get("a")
        self.get("b")
        self.clock.now = at(12, 36)
        self.get("c")  # stores under the lock and sweeps a and b, which expired at 12:35
        self.assertEqual(list(self.cache._entries), [self.cache.key("c", None)])

    def test_size_is_capped_and_the_earliest_expiry_goes_first(self):
        self.get("old")  # stored 12:10, expires 12:35
        self.clock.now = at(12, 36)  # the next entries expire 13:05
        with mock.patch.object(cache, "MAX_ENTRIES", 3):
            for i in range(5):
                self.get("e", {"i": i})
        self.assertEqual(len(self.cache._entries), 3)
        self.assertNotIn(self.cache.key("old", None), self.cache._entries)
        self.assertEqual(self.get("e", {"i": 4}), 6)  # still cached: no extra compute

    def flight_pair(self, leader_compute, waiter_compute):
        """Run a leader and then a waiter on one key; return (leader, waiter) outcome dicts once both are done.

        The waiter starts only after the leader is inside its compute, and the leader is released only after the
        waiter has entered the in-flight Event's wait(): `cache.threading.Event` is swapped for a subclass that
        reports that. So the waiter provably blocked on the flight instead of finding a stored entry.
        """
        in_wait = threading.Event()  # created before the swap: a plain Event

        class RecordingEvent(threading.Event):
            def wait(self, timeout=None):
                in_wait.set()
                return super().wait(timeout)

        fake_threading = types.SimpleNamespace(Lock=threading.Lock, Event=RecordingEvent)
        entered, release = threading.Event(), threading.Event()
        out = {"leader": {}, "waiter": {}}

        def run(name, compute):
            try:
                out[name]["value"] = self.cache.get_or_compute("e", None, compute)
            except BaseException as exc:  # noqa: BLE001 - recorded and asserted by the caller
                out[name]["error"] = exc

        def leader():
            entered.set()
            self.assertTrue(release.wait(5))
            return leader_compute()

        with mock.patch.object(cache, "threading", fake_threading):
            first = threading.Thread(target=run, args=("leader", leader))
            first.start()
            self.assertTrue(entered.wait(5))
            self.assertIn(self.cache.key("e", None), self.cache._inflight)
            second = threading.Thread(target=run, args=("waiter", waiter_compute))
            second.start()
            self.assertTrue(in_wait.wait(5), "the second caller never reached the in-flight wait")
            release.set()
            first.join(5)
            second.join(5)
        self.assertFalse(first.is_alive() or second.is_alive())
        return out["leader"], out["waiter"]

    def test_concurrent_callers_of_one_key_share_one_compute(self):
        calls = []

        def compute():
            calls.append("leader")
            return "value"

        def waiter_compute():
            calls.append("waiter")
            return "waiter's own"

        leader, waiter = self.flight_pair(compute, waiter_compute)
        self.assertEqual((leader, waiter), ({"value": "value"}, {"value": "value"}))
        self.assertEqual(calls, ["leader"])  # the waiter never computed
        self.assertEqual(self.cache._inflight, {})

    def test_waiter_recomputes_when_the_leader_fails_and_the_leader_sees_the_error(self):
        def boom():
            raise RuntimeError("bq down")

        leader, waiter = self.flight_pair(boom, lambda: "recovered")
        self.assertEqual(waiter, {"value": "recovered"})
        self.assertEqual(list(leader), ["error"])
        self.assertIsInstance(leader["error"], RuntimeError)
        self.assertEqual(self.cache._inflight, {})
        self.assertEqual(self.cache.get_or_compute("e", None, lambda: "not called"), "recovered")  # cached by the waiter

    def test_a_failed_compute_is_not_cached_or_shared_and_clears_the_flight(self):
        def boom():
            raise RuntimeError("bq down")

        with self.assertRaises(RuntimeError):
            self.cache.get_or_compute("e", None, boom)
        self.assertEqual(self.get(), 1)  # the next caller computes afresh
        self.assertEqual(self.cache._inflight, {})

    def test_clear(self):
        self.get()
        self.cache.clear()
        self.assertEqual(self.get(), 2)


if __name__ == "__main__":
    unittest.main()
