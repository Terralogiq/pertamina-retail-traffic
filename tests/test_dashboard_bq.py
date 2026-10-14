"""bq.query_all runs independent queries concurrently and keeps the order; JSON responses are gzipped."""
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import bq, cache  # noqa: E402
from dashboard.api.main import app  # noqa: E402


class QueryAllTest(unittest.TestCase):
    def test_results_follow_the_order_given(self):
        def fake(sql, params=None):
            return [{"sql": sql, "params": params}]

        with mock.patch.object(bq, "query", fake):
            first, second = bq.query_all(("a", {"x": 1}), ("b", None))
        self.assertEqual(first, [{"sql": "a", "params": {"x": 1}}])
        self.assertEqual(second, [{"sql": "b", "params": None}])

    def test_queries_overlap(self):
        # Each query waits for the other to start: sequential execution would time out on the barrier.
        barrier = threading.Barrier(2, timeout=5)

        def fake(sql, params=None):
            barrier.wait()
            return [sql]

        with mock.patch.object(bq, "query", fake):
            self.assertEqual(bq.query_all(("a", None), ("b", None)), [["a"], ["b"]])

    def test_an_error_in_one_query_propagates(self):
        def fake(sql, params=None):
            if sql == "bad":
                raise RuntimeError("bq down")
            return []

        with mock.patch.object(bq, "query", fake), self.assertRaises(RuntimeError):
            bq.query_all(("ok", None), ("bad", None))


class GzipTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "pw"})
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.default.clear()
        self.addCleanup(cache.default.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/api/login", json={"password": "pw"})

    def test_large_api_responses_are_gzipped_and_small_ones_are_not(self):
        big = [{"site_id": f"s{i}", "leg": "approach", "precipitation_mm": 1.5, "congestion_index": 1.2}
               for i in range(200)]
        with mock.patch("dashboard.api.bq.query", return_value=big):
            res = self.client.get("/api/weather/latest", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(res.headers["content-encoding"], "gzip")
        self.assertEqual(res.json(), big)  # the client decodes transparently
        self.assertNotIn("content-encoding", self.client.get("/health", headers={"Accept-Encoding": "gzip"}).headers)


if __name__ == "__main__":
    unittest.main()
