"""GET /api/traffic/{latest,series,pattern,typical-day} with BigQuery mocked."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import cache  # noqa: E402
from dashboard.api.main import app  # noqa: E402
from dashboard.api.routers import traffic  # noqa: E402

SITE = "74.902.22"
SITES = [{"site_id": SITE}, {"site_id": "34.121.03"}]
SLOT = datetime(2026, 10, 7, 3, 30, tzinfo=timezone.utc)


def point(leg="approach", **kw):
    base = {"selected_route_id": f"r-{leg}", "site_id": SITE, "leg": leg, "slot_time": SLOT,
            "duration_s": 120.0, "delay_s": 20.0, "congestion_index": 1.2, "speed_kmh": 30.0,
            "baseline_samples": 100}
    return {**base, **kw}


class FakeBq:
    """Stands in for bq.query: sites rows for the /api/sites query, `rows` for any traffic query.

    A typical-day request also counts distinct local dates. That query is recognised by COUNT(DISTINCT
    and returns `days`, so the hour rows and the day count can differ.
    """

    def __init__(self, rows=(), days=0):
        self.rows = list(rows)
        self.days = days
        self.calls = []  # (sql, params) of the traffic queries only

    def __call__(self, sql, params=None):
        if "ST_ASGEOJSON" in sql:
            return [{"site_id": s["site_id"], "name": "", "place_id": "", "road_name": "", "city": "",
                     "timezone": "Asia/Makassar", "lat": 0, "lng": 0, "selected_route_id": None}
                    for s in SITES]
        self.calls.append((sql, params))
        if "COUNT(DISTINCT" in sql:
            return [{"days": self.days}]
        return self.rows


class TrafficTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "pw"})
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.default.clear()
        self.addCleanup(cache.default.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/api/login", json={"password": "pw"})

    def get(self, url, rows=(), days=0):
        fake = FakeBq(rows, days=days)
        with mock.patch("dashboard.api.bq.query", fake):
            res = self.client.get(url)
        return res, fake

    def test_latest_shape(self):
        rows = [point("approach"), point("departure", duration_s=None, delay_s=None, congestion_index=None,
                                         speed_kmh=None, baseline_samples=None)]
        res, fake = self.get("/api/traffic/latest", rows)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()[0], {
            "selected_route_id": "r-approach", "site_id": SITE, "leg": "approach",
            "slot_time": "2026-10-07T03:30:00Z", "duration_s": 120.0, "delay_s": 20.0,
            "congestion_index": 1.2, "speed_kmh": 30.0, "baseline_samples": 100})
        departure = res.json()[1]
        for key in ("duration_s", "delay_s", "congestion_index", "speed_kmh", "baseline_samples"):
            self.assertIsNone(departure[key])
        sql = fake.calls[0][0]
        self.assertIn("slot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)", sql)
        self.assertIn("ROW_NUMBER() OVER (PARTITION BY t.selected_route_id ORDER BY t.slot_time DESC) = 1", sql)
        self.assertIn("r.active", sql)

    def test_latest_is_cached(self):
        fake = FakeBq([point()])
        with mock.patch("dashboard.api.bq.query", fake):
            self.client.get("/api/traffic/latest")
            self.client.get("/api/traffic/latest")
        self.assertEqual(len(fake.calls), 1)

    def test_series_params_and_default_window(self):
        before = cache.utc_now()
        res, fake = self.get(f"/api/traffic/series?site_id={SITE}", [point(), point("departure")])
        self.assertEqual(res.status_code, 200)
        self.assertEqual([p["leg"] for p in res.json()], ["approach", "departure"])
        sql, params = fake.calls[0]
        self.assertIn("t.slot_time >= @from_ts AND t.slot_time <= @to_ts", sql)
        self.assertIn("r.site_id = @site_id", sql)
        self.assertEqual(params["site_id"], SITE)
        self.assertEqual(params["to_ts"] - params["from_ts"], timedelta(hours=24))
        self.assertGreaterEqual(params["to_ts"], before)

    def test_series_explicit_range_normalised_to_utc(self):
        res, fake = self.get(f"/api/traffic/series?site_id={SITE}"
                             "&from=2026-10-01T00:00:00%2B07:00&to=2026-10-02T00:00:00Z")
        self.assertEqual(res.status_code, 200)
        params = fake.calls[0][1]
        self.assertEqual(params["from_ts"], datetime(2026, 9, 30, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(params["to_ts"], datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc))

    def test_series_bad_ranges_are_400(self):
        base = f"/api/traffic/series?site_id={SITE}"
        for query in ("&from=yesterday", "&to=nope",
                      "&from=2026-10-02T00:00:00Z&to=2026-10-01T00:00:00Z",
                      "&from=2026-10-01T00:00:00Z&to=2026-10-01T00:00:00Z",
                      "&from=2026-08-31T00:00:00Z&to=2026-10-02T00:00:00Z"):  # 32 d
            with self.subTest(query=query):
                res, fake = self.get(base + query)
                self.assertEqual(res.status_code, 400)
                self.assertEqual(fake.calls, [])

    def test_series_cap_is_31_days_inclusive(self):
        res, _ = self.get(f"/api/traffic/series?site_id={SITE}"
                          "&from=2026-09-01T00:00:00Z&to=2026-10-02T00:00:00Z")
        self.assertEqual(res.status_code, 200)

    def test_unknown_site_is_404(self):
        for path in ("series", "pattern", "typical-day"):
            with self.subTest(path=path):
                res, fake = self.get(f"/api/traffic/{path}?site_id=nope")
                self.assertEqual(res.status_code, 404)
                self.assertEqual(fake.calls, [])

    def test_pattern_sql_uses_site_timezone(self):
        rows = [{"dow": 1, "hour": 8, "leg": "approach", "mean_congestion": 1.4, "mean_speed_kmh": 25.0, "n": 4}]
        res, fake = self.get(f"/api/traffic/pattern?site_id={SITE}", rows)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), rows)
        sql, params = fake.calls[0]
        self.assertIn("EXTRACT(HOUR FROM t.slot_time AT TIME ZONE s.timezone)", sql)
        self.assertIn("EXTRACT(DAYOFWEEK FROM t.slot_time AT TIME ZONE s.timezone)", sql)
        self.assertIn("JOIN `gcp-coe-sandbox.traffic.sites` AS s ON s.site_id = r.site_id", sql)
        self.assertNotIn("Asia/", sql)  # never a hard-coded zone
        self.assertIn("t.slot_time >= @from_ts", sql)
        self.assertEqual(params["to_ts"] - params["from_ts"], timedelta(days=28))

    def test_pattern_dow_is_monday_first(self):
        # BigQuery DAYOFWEEK: Sunday = 1 ... Saturday = 7. The SQL maps it to Monday = 1 ... Sunday = 7.
        mapped = {bq_dow: (bq_dow + 5) % 7 + 1 for bq_dow in range(1, 8)}
        self.assertEqual(mapped, {1: 7, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6})
        self.assertIn("MOD(EXTRACT(DAYOFWEEK FROM t.slot_time AT TIME ZONE s.timezone) + 5, 7) + 1", traffic.PATTERN_SQL)

    def test_pattern_days_bounds(self):
        for days, status in ((0, 400), (29, 400), (1, 200), (28, 200)):
            with self.subTest(days=days):
                res, _ = self.get(f"/api/traffic/pattern?site_id={SITE}&days={days}")
                self.assertEqual(res.status_code, status)

    def test_core_columns_only(self):
        for sql in (traffic.LATEST_SQL, traffic.SERIES_SQL, traffic.PATTERN_SQL,
                    traffic.TYPICAL_SQL, traffic.TYPICAL_DAYS_SQL):
            self.assertNotIn("static_ratio", sql)
            self.assertNotIn("demo_", sql)

    def test_typical_day_payload_and_sql(self):
        rows = [
            {"leg": "approach", "day_kind": "weekday", "hour": 8, "median_delay_s": 40.0,
             "p25_delay_s": 20.0, "p75_delay_s": 60.0, "n": 2},
            {"leg": "approach", "day_kind": "weekday", "hour": 9, "median_delay_s": 10.0,
             "p25_delay_s": 5.0, "p75_delay_s": 15.0, "n": 6},
        ]
        res, fake = self.get(f"/api/traffic/typical-day?site_id={SITE}", rows, days=6)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["days"], 6)
        self.assertFalse(body["ready"])
        weekday = next(leg for leg in body["legs"] if leg["leg"] == "approach" and leg["day_kind"] == "weekday")
        self.assertEqual(len(weekday["hours"]), 24)
        by_hour = {hour["hour"]: hour for hour in weekday["hours"]}
        self.assertEqual(by_hour[8]["n"], 2)
        self.assertTrue(by_hour[8]["faded"])
        self.assertEqual(by_hour[8]["median_delay_s"], 40.0)
        self.assertFalse(by_hour[9]["faded"])
        self.assertEqual(by_hour[0]["n"], 0)
        self.assertTrue(by_hour[0]["faded"])
        weekend = next(leg for leg in body["legs"] if leg["leg"] == "approach" and leg["day_kind"] == "weekend")
        self.assertTrue(all(hour["n"] == 0 and hour["faded"] for hour in weekend["hours"]))
        hour_sql, params = next((sql, p) for sql, p in fake.calls if "APPROX_QUANTILES" in sql)
        self.assertIn("DATE '2026-08-17'", hour_sql)
        self.assertNotIn("DATE '2026-02-16'", hour_sql)
        self.assertIn("EXTRACT(DAYOFWEEK FROM t.slot_time AT TIME ZONE s.timezone) IN (1, 7)", hour_sql)
        self.assertIn("EXTRACT(HOUR FROM t.slot_time AT TIME ZONE s.timezone)", hour_sql)
        self.assertNotIn("Asia/", hour_sql)
        self.assertEqual(params["to_ts"] - params["from_ts"], timedelta(days=28))
        days_sql = next(sql for sql, _ in fake.calls if "COUNT(DISTINCT" in sql)
        self.assertIn("DATE(t.slot_time, s.timezone)", days_sql)
        self.assertIn("t.slot_time >= @from_ts", days_sql)

    def test_typical_day_ready_at_seven_days_and_empty_site(self):
        res, _ = self.get(f"/api/traffic/typical-day?site_id={SITE}", days=7)
        self.assertTrue(res.json()["ready"])
        self.assertEqual(res.json()["legs"], [])
        # The payload is cached per site, so the empty case needs a fresh entry.
        cache.default.clear()
        empty, _ = self.get(f"/api/traffic/typical-day?site_id={SITE}", days=0)
        self.assertEqual(empty.json(), {"days": 0, "ready": False, "legs": []})

    def test_need_login(self):
        self.client.cookies.clear()
        for path in ("latest", "series?site_id=x", "pattern?site_id=x", "typical-day?site_id=x"):
            self.assertEqual(self.client.get(f"/api/traffic/{path}").status_code, 401)


if __name__ == "__main__":
    unittest.main()
