"""GET /api/places/{site_id} with BigQuery mocked."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import cache  # noqa: E402
from dashboard.api.main import app  # noqa: E402
from dashboard.api.routers import places  # noqa: E402

NOW = datetime(2026, 10, 8, 3, 10, tzinfo=timezone.utc)
FETCHED = datetime(2026, 10, 7, 2, 46, 13, 474034, tzinfo=timezone.utc)


def review(day, author):
    return {"rating": 5, "text": f"ok {author}", "language": "id",
            "publish_time": datetime(2026, 9, day, 5, 0, tzinfo=timezone.utc), "author_name": author}


DETAILS = {
    "run_id": "run-2", "fetched_at": FETCHED, "display_name": "SPBU 34.121.03", "rating": 4.4,
    "user_rating_count": 1655, "business_status": "OPERATIONAL", "open_now": True,
    "weekday_descriptions": ["Senin: Buka 24 jam"],
    "reviews": [review(1, "old"), review(20, "new"), review(10, "mid")],
}


def nearby(radius, brand, count, is_self=False):
    return {"radius_m": radius, "brand": brand, "is_self": is_self, "count": count}


# 1 km: 3 results incl. self; 3 km: 20 results incl. self (capped)
NEARBY = [nearby(1000, "Pertamina", 1, is_self=True), nearby(1000, "Shell", 1), nearby(1000, "other", 1),
          nearby(3000, "Pertamina", 1, is_self=True), nearby(3000, "Pertamina", 5), nearby(3000, "BP", 3),
          nearby(3000, "other", 11)]
POI = [{"place_type": "atm", "radius_m": 500, "count": 1}, {"place_type": "atm", "radius_m": 1000, "count": 4}]


def fake_query(details=None, nearby_rows=None, poi=None):
    def run(sql, params=None):
        if "places_details" in sql:
            return [details] if details else []
        if "places_nearby" in sql:
            return nearby_rows or []
        if "places_aggregate" in sql:
            return poi or []
        raise AssertionError(sql)
    return run


class PlacesTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "pw"})
        patcher.start()
        self.addCleanup(patcher.stop)
        clock = mock.patch("dashboard.api.cache.utc_now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        sites = mock.patch("dashboard.api.routers.traffic.get_sites", return_value=[{"site_id": "34.121.03"}])
        sites.start()
        self.addCleanup(sites.stop)
        cache.default.clear()
        self.addCleanup(cache.default.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/api/login", json={"password": "pw"})

    def get(self, url="/api/places/34.121.03", **rows):
        with mock.patch("dashboard.api.bq.query", side_effect=fake_query(**rows)) as q:
            return self.client.get(url), q

    def test_needs_login(self):
        res = TestClient(app, base_url="https://testserver").get("/api/places/34.121.03")
        self.assertEqual(res.status_code, 401)

    def test_unknown_site_is_404_and_skips_bigquery(self):
        res, q = self.get("/api/places/nope", details=DETAILS)
        self.assertEqual(res.status_code, 404)
        q.assert_not_called()

    def test_response_shape(self):
        res, _ = self.get(details=DETAILS, nearby_rows=NEARBY, poi=POI)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["site_id"], "34.121.03")
        self.assertEqual(body["run_id"], "run-2")
        self.assertEqual(body["fetched_at"], "2026-10-07T02:46:13.474034Z")
        d = body["details"]
        self.assertEqual((d["display_name"], d["rating"], d["user_rating_count"], d["open_now"]),
                         ("SPBU 34.121.03", 4.4, 1655, True))
        self.assertEqual(d["weekday_descriptions"], ["Senin: Buka 24 jam"])
        self.assertEqual([r["author_name"] for r in d["reviews"]], ["new", "mid", "old"])  # newest first
        self.assertEqual(d["reviews"][0], {"rating": 5, "text": "ok new", "language": "id",
                                           "publish_time": "2026-09-20T05:00:00Z", "author_name": "new"})
        self.assertEqual(body["poi"][1], {"place_type": "atm", "radius_m": 1000, "count": 4})

    def test_competitors_exclude_self_list_every_brand_and_flag_the_cap(self):
        res, _ = self.get(details=DETAILS, nearby_rows=NEARBY)
        body = res.json()
        by = {(c["radius_m"], c["brand"]): c["count"] for c in body["competitors"]}
        self.assertEqual(len(body["competitors"]), 2 * 5)
        self.assertEqual([c["brand"] for c in body["competitors"][:5]], list(places.BRANDS))
        self.assertEqual((by[1000, "Pertamina"], by[1000, "Shell"], by[1000, "BP"], by[1000, "other"]), (0, 1, 0, 1))
        self.assertEqual((by[3000, "Pertamina"], by[3000, "BP"], by[3000, "other"]), (5, 3, 11))
        self.assertEqual(body["competitor_totals"], [{"radius_m": 1000, "total": 2, "capped": False},
                                                     {"radius_m": 3000, "total": 19, "capped": True}])

    def test_capped_counts_the_site_itself(self):
        # 19 competitors + self = 20 results: capped. 19 results incl. self: not.
        full = [nearby(1000, "other", 19), nearby(1000, "Pertamina", 1, is_self=True)]
        short = [nearby(1000, "other", 18), nearby(1000, "Pertamina", 1, is_self=True)]
        self.assertEqual(places.competitors(full)[1], [{"radius_m": 1000, "total": 19, "capped": True}])
        self.assertEqual(places.competitors(short)[1], [{"radius_m": 1000, "total": 18, "capped": False}])

    def test_no_run_in_window_gives_empty_payload(self):
        res, q = self.get()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIsNone(body["run_id"])
        self.assertIsNone(body["details"])
        self.assertEqual((body["competitors"], body["poi"]), ([], []))
        self.assertEqual(q.call_count, 1)  # nothing to read by run_id

    def test_every_query_filters_fetched_at_and_later_ones_pin_the_run(self):
        _, q = self.get(details=DETAILS, nearby_rows=NEARBY, poi=POI)
        self.assertEqual(q.call_count, 3)
        since = NOW - timedelta(days=places.LOOKBACK_DAYS)
        for call in q.call_args_list:
            sql, params = call.args
            self.assertIn("fetched_at >= @since", sql)
            self.assertEqual(params["since"], since)
            self.assertEqual(params["site_id"], "34.121.03")
        self.assertIn("ORDER BY fetched_at DESC", q.call_args_list[0].args[0])
        for call in q.call_args_list[1:]:
            self.assertIn("run_id = @run_id", call.args[0])
            self.assertEqual(call.args[1]["run_id"], "run-2")
        self.assertIn("n.place_id = s.place_id", q.call_args_list[1].args[0])

    def test_nearby_keeps_only_the_latest_attempt_per_radius(self):
        # a retry under one run_id leaves stale rows at the older fetched_at; they must not reach the counts
        _, q = self.get(details=DETAILS, nearby_rows=NEARBY)
        sql = q.call_args_list[1].args[0]
        self.assertIn("QUALIFY n.fetched_at = MAX(n.fetched_at) OVER (PARTITION BY n.site_id, n.radius_m)", sql)
        self.assertLess(sql.index("QUALIFY"), sql.index("GROUP BY"))  # filter first, aggregate after

    def test_cached(self):
        with mock.patch("dashboard.api.bq.query", side_effect=fake_query(details=DETAILS)) as q:
            self.client.get("/api/places/34.121.03")
            self.client.get("/api/places/34.121.03")
        self.assertEqual(q.call_count, 3)  # one request's three queries; the second request hit the cache


if __name__ == "__main__":
    unittest.main()
