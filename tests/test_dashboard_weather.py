"""GET /api/weather/latest, /api/weather/series and /api/rain with BigQuery mocked."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import cache  # noqa: E402
from dashboard.api.main import app  # noqa: E402
from dashboard.api.routers import weather  # noqa: E402

NOW = datetime(2026, 10, 7, 3, 10, tzinfo=timezone.utc)

RAIN_ROW = {"site_id": "34.121.03", "leg": "approach",
            "rain_mean_delay_s": 41.5, "rain_n": 12, "dry_mean_delay_s": 20.0, "dry_n": 300,
            "demo_rain_mean_delay_s": 38.0, "demo_rain_n": 20, "demo_dry_mean_delay_s": 19.0, "demo_dry_n": 292}


def rain_queries(scatter):
    """Stands in for bq.query on /api/rain, whose two queries run concurrently: answer by SQL, not by call order."""
    return lambda sql, params=None: scatter if "w.precipitation_mm" in sql else [RAIN_ROW]


class WeatherTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "pw"})
        patcher.start()
        self.addCleanup(patcher.stop)
        clock = mock.patch.object(weather, "utc_now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        sites = mock.patch("dashboard.api.routers.traffic.get_sites",
                           return_value=[{"site_id": "1"}, {"site_id": "34.121.03"}])
        sites.start()
        self.addCleanup(sites.stop)
        cache.default.clear()
        self.addCleanup(cache.default.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/api/login", json={"password": "pw"})

    def get(self, url, rows=None):
        with mock.patch("dashboard.api.bq.query", return_value=rows or []) as q:
            res = self.client.get(url)
        return res, q

    def test_latest_filters_slot_time_to_last_two_hours_and_is_cached(self):
        row = {"site_id": "1", "slot_time": NOW, "temperature_c": 29.1, "demo_condition_text": "Light rain"}
        with mock.patch("dashboard.api.bq.query", return_value=[row]) as q:
            res = self.client.get("/api/weather/latest")
            self.client.get("/api/weather/latest")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()[0]["demo_condition_text"], "Light rain")
        self.assertEqual(q.call_count, 1)
        sql, params = q.call_args.args
        self.assertIn("slot_time >= @start", sql)
        self.assertIn("ROW_NUMBER() OVER (PARTITION BY site_id ORDER BY slot_time DESC) = 1", sql)
        self.assertEqual(params, {"start": NOW - timedelta(hours=2)})

    def test_series_defaults_to_last_24_hours(self):
        res, q = self.get("/api/weather/series?site_id=1")
        self.assertEqual(res.status_code, 200)
        sql, params = q.call_args.args
        self.assertIn("slot_time >= @start AND slot_time < @end", sql)
        self.assertEqual(params, {"site_id": "1", "start": NOW - timedelta(hours=24), "end": NOW})

    def test_series_explicit_range_naive_is_utc(self):
        res, q = self.get("/api/weather/series?site_id=1&from=2026-10-01T00:00:00&to=2026-10-02T00:00:00Z")
        self.assertEqual(res.status_code, 200)
        params = q.call_args.args[1]
        self.assertEqual(params["start"], datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(params["end"], datetime(2026, 10, 2, tzinfo=timezone.utc))

    def test_series_bad_params_are_400_and_skip_bigquery(self):
        for url in ("/api/weather/series",
                    "/api/weather/series?site_id=1&from=yesterday",
                    "/api/weather/series?site_id=1&to=nope",
                    "/api/weather/series?site_id=1&from=2026-10-02T00:00:00Z&to=2026-10-01T00:00:00Z",
                    "/api/weather/series?site_id=1&from=2026-08-01T00:00:00Z&to=2026-10-01T00:00:00Z"):
            with self.subTest(url=url):
                res, q = self.get(url)
                self.assertEqual(res.status_code, 400)
                q.assert_not_called()

    def test_series_range_cap_is_31_days_inclusive(self):
        res, _ = self.get("/api/weather/series?site_id=1&from=2026-09-01T00:00:00Z&to=2026-10-02T00:00:00Z")
        self.assertEqual(res.status_code, 200)
        res, _ = self.get("/api/weather/series?site_id=1&from=2026-09-01T00:00:00Z&to=2026-10-02T00:00:01Z")
        self.assertEqual(res.status_code, 400)

    def test_rain_all_sites_splits_core_and_demo(self):
        scatter = [{"site_id": "34.121.03", "leg": "approach", "precipitation_mm": 1.2, "congestion_index": 1.4}]
        with mock.patch("dashboard.api.bq.query", side_effect=rain_queries(scatter)) as q:
            res = self.client.get("/api/rain")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["days"], 28)
        self.assertIsNone(body["site_id"])
        self.assertEqual(body["core"], [{"site_id": "34.121.03", "leg": "approach",
                                         "rain": {"mean_delay_s": 41.5, "n": 12},
                                         "dry": {"mean_delay_s": 20.0, "n": 300}}])
        self.assertEqual(body["demo"][0]["rain"], {"mean_delay_s": 38.0, "n": 20})
        self.assertEqual(body["demo"][0]["dry"], {"mean_delay_s": 19.0, "n": 292})
        self.assertEqual(body["scatter"], scatter)
        for call in q.call_args_list:
            sql, params = call.args
            self.assertIn("v.slot_time >= @start", sql)
            self.assertIn("w.slot_time >= @start", sql)
            self.assertIn("w.site_id = r.site_id AND w.slot_time = v.slot_time", sql)
            self.assertNotIn("@site_id", sql)
            self.assertIn("r.selected_route_id = v.selected_route_id AND r.active", sql)
            self.assertEqual(params, {"start": NOW - timedelta(days=28)})

    def test_rain_one_site_adds_a_parameterised_filter(self):
        with mock.patch("dashboard.api.bq.query", side_effect=rain_queries([])) as q:
            res = self.client.get("/api/rain?site_id=34.121.03&days=7")
        self.assertEqual(res.json()["site_id"], "34.121.03")
        for call in q.call_args_list:
            sql, params = call.args
            self.assertIn("r.site_id = @site_id", sql)
            self.assertNotIn("34.121.03", sql)
            self.assertEqual(params, {"start": NOW - timedelta(days=7), "site_id": "34.121.03"})

    def test_unknown_site_is_404_and_skips_bigquery(self):
        for url in ("/api/weather/series?site_id=nope", "/api/rain?site_id=nope"):
            with self.subTest(url=url):
                res, q = self.get(url)
                self.assertEqual(res.status_code, 404)
                q.assert_not_called()

    def test_rain_bad_days_is_400(self):
        for days in ("0", "29", "-1", "x", "1.5"):
            with self.subTest(days=days):
                res, q = self.get(f"/api/rain?days={days}")
                self.assertEqual(res.status_code, 400)
                q.assert_not_called()

    def test_rain_days_boundaries_ok(self):
        for days in ("1", "28"):
            with self.subTest(days=days):
                cache.default.clear()
                with mock.patch("dashboard.api.bq.query", return_value=[]):
                    self.assertEqual(self.client.get(f"/api/rain?days={days}").status_code, 200)

    def test_rain_is_cached_per_params(self):
        with mock.patch("dashboard.api.bq.query", return_value=[]) as q:
            self.client.get("/api/rain?days=7")
            self.client.get("/api/rain?days=7")
            self.client.get("/api/rain?days=14")
        self.assertEqual(q.call_count, 4)  # summary + scatter, twice

    def test_need_login(self):
        self.client.cookies.clear()
        for url in ("/api/weather/latest", "/api/weather/series?site_id=1", "/api/rain"):
            with self.subTest(url=url):
                res, q = self.get(url)
                self.assertEqual(res.status_code, 401)
                q.assert_not_called()


if __name__ == "__main__":
    unittest.main()
