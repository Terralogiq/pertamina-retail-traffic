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
    and returns `days`, so the hour rows and the day count can differ. The per-hour queue-risk query is
    recognised by its GROUP BY day_kind, hour and returns `hours`.
    """

    def __init__(self, rows=(), days=0, hours=()):
        self.rows = list(rows)
        self.days = days
        self.hours = list(hours)
        self.calls = []  # (sql, params) of the traffic queries only

    def __call__(self, sql, params=None):
        if "ST_ASGEOJSON" in sql:
            return [{"site_id": s["site_id"], "name": "", "place_id": "", "road_name": "", "city": "",
                     "timezone": "Asia/Makassar", "lat": 0, "lng": 0, "selected_route_id": None}
                    for s in SITES]
        self.calls.append((sql, params))
        if "COUNT(DISTINCT" in sql:
            return [{"days": self.days}]
        if "GROUP BY day_kind, hour" in sql:
            return self.hours
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

    def get(self, url, rows=(), days=0, hours=()):
        fake = FakeBq(rows, days=days, hours=hours)
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
        self.assertTrue(all(hour["n"] == 0 and hour["faded"] and not hour["busy"] for hour in weekend["hours"]))
        self.assertFalse(by_hour[8]["busy"])
        self.assertEqual(weekday["windows"], [])
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
        # A failed slot has a null delay. It must not inflate n, fade, or the day count.
        self.assertIn("t.delay_s IS NOT NULL", hour_sql)
        self.assertIn("t.delay_s IS NOT NULL", days_sql)
        self.assertIn("COUNTIF", hour_sql)
        self.assertIn("t.congestion_index >= 1.5", hour_sql)
        self.assertIn("baseline_samples, 0) >= 302", hour_sql)
        self.assertIn("duration_in_seconds", hour_sql)
        self.assertIn("t.delay_s >= @gate_s", hour_sql)
        self.assertIn("@provisional_kmh", hour_sql)
        self.assertNotIn("road_type", hour_sql)
        self.assertEqual(params["gate_s"], 20)
        self.assertEqual(params["provisional_kmh"], 45)

    def test_busy_windows_wait_until_ready(self):
        rows = [
            {"leg": "approach", "day_kind": "weekday", "hour": 7, "median_delay_s": 40.0,
             "p25_delay_s": 20.0, "p75_delay_s": 60.0, "n": 4, "slow_n": 3},
            {"leg": "approach", "day_kind": "weekday", "hour": 8, "median_delay_s": 120.0,
             "p25_delay_s": 80.0, "p75_delay_s": 160.0, "n": 4, "slow_n": 3},
            {"leg": "approach", "day_kind": "weekday", "hour": 9, "median_delay_s": 20.0,
             "p25_delay_s": 10.0, "p75_delay_s": 30.0, "n": 4, "slow_n": 3},
        ]
        early, _ = self.get(f"/api/traffic/typical-day?site_id={SITE}", rows, days=6)
        early_leg = next(leg for leg in early.json()["legs"] if leg["day_kind"] == "weekday")
        early_hours = {hour["hour"]: hour for hour in early_leg["hours"]}
        self.assertTrue(early_hours[7]["busy"])
        self.assertFalse(early_hours[9]["busy"])
        self.assertEqual(early_leg["windows"], [])
        cache.default.clear()
        ready, _ = self.get(f"/api/traffic/typical-day?site_id={SITE}", rows, days=7)
        ready_leg = next(leg for leg in ready.json()["legs"] if leg["day_kind"] == "weekday")
        self.assertEqual(ready_leg["windows"], [{"start_hour": 7, "end_hour": 9, "median_delay_s": 80.0}])

    def test_typical_day_ready_at_seven_days_and_empty_site(self):
        res, _ = self.get(f"/api/traffic/typical-day?site_id={SITE}", days=7)
        self.assertTrue(res.json()["ready"])
        self.assertEqual(res.json()["legs"], [])
        # The payload is cached per site, so the empty case needs a fresh entry.
        cache.default.clear()
        empty, _ = self.get(f"/api/traffic/typical-day?site_id={SITE}", days=0)
        self.assertEqual(empty.json(), {"days": 0, "ready": False, "legs": []})

    def test_queue_risk_payload_order_and_confidence(self):
        def row(site_id, als, both, dep, days, median):
            return {"site_id": site_id, "als_pct": als, "both_slow_pct": both, "departure_only_pct": dep,
                    "days_with_2h_als": days, "full_days": 7, "als_median_delay_s": median}
        rows = [row("34.401.16", 0.0, 33.6, 27.3, 0, None), row("unlisted", 0.0, 0.0, 0.0, 0, None),
                row("34.121.03", 19.7, 3.0, 0.0, 6, 25.0), row("54.801.17", 29.8, 10.7, 2.2, 7, 75.0)]
        res, fake = self.get("/api/traffic/queue-risk", rows)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(set(body), {"window_days", "sites"})
        self.assertEqual(body["window_days"], 28)
        self.assertEqual([s["site_id"] for s in body["sites"]], ["54.801.17", "34.121.03", "unlisted", "34.401.16"])
        self.assertEqual([s["tier"] for s in body["sites"]], ["strong", "moderate", "none", "cannot_tell"])
        pemogan = body["sites"][0]
        self.assertEqual(set(pemogan), {"site_id", "tier", "als_pct", "both_slow_pct", "departure_only_pct",
                                        "days_with_2h_als", "full_days", "als_median_delay_s", "confidence"})
        self.assertEqual(pemogan["confidence"]["level"], "medium")
        self.assertEqual(set(pemogan["confidence"]), {"level", "reason", "as_of"})
        self.assertEqual((pemogan["als_pct"], pemogan["days_with_2h_als"], pemogan["als_median_delay_s"]),
                         (29.8, 7, 75.0))
        self.assertIsNone(body["sites"][2]["confidence"])  # a site with no reviewed entry
        self.assertIsNone(body["sites"][3]["als_median_delay_s"])
        self.assertEqual(len(fake.calls), 1)  # one job for all sites

    def test_queue_risk_empty_when_no_readings(self):
        res, _ = self.get("/api/traffic/queue-risk")
        self.assertEqual(res.json(), {"window_days": 28, "sites": []})

    def test_queue_risk_sql_window_band_rule_and_core_columns(self):
        _, fake = self.get("/api/traffic/queue-risk")
        sql, params = fake.calls[0]
        self.assertEqual(params["to_ts"] - params["from_ts"], timedelta(days=28))
        self.assertIn("t.slot_time >= @from_ts AND t.slot_time <= @to_ts", sql)
        self.assertIn("r.active", sql)
        self.assertIn("t.delay_s IS NOT NULL", sql)
        self.assertNotIn("static_ratio", sql)
        self.assertNotIn("demo_", sql)
        self.assertNotIn("Asia/", sql)
        # band rule is busy.slow_count_sql() with the road class per site, never one gate for all
        self.assertIn("t.congestion_index >= 1.5", sql)
        self.assertIn("baseline_samples, 0) >= 302", sql)
        self.assertIn("IF(LOWER(s.road_type) LIKE '%toll%', @toll_gate_s, @urban_gate_s)", sql)
        self.assertIn("IF(LOWER(s.road_type) LIKE '%toll%', @toll_provisional_kmh, @urban_provisional_kmh)", sql)
        self.assertNotIn("@gate_s", sql)
        self.assertNotIn("@provisional_kmh", sql)
        self.assertEqual((params["urban_gate_s"], params["toll_gate_s"]), (20, 30))
        self.assertEqual((params["urban_provisional_kmh"], params["toll_provisional_kmh"]), (45, 80))
        self.assertIn("n >= 40 AND als_n >= 4", sql)

    def test_queue_risk_is_cached(self):
        fake = FakeBq()
        with mock.patch("dashboard.api.bq.query", fake):
            self.client.get("/api/traffic/queue-risk")
            self.client.get("/api/traffic/queue-risk")
        self.assertEqual(len(fake.calls), 1)

    def test_queue_risk_all_sites_is_unchanged_by_the_site_filter(self):
        # The overview's call: no site_id, one job, no per-site fields.
        row = {"site_id": SITE, "als_pct": 5.0, "both_slow_pct": 1.0, "departure_only_pct": 1.0,
               "days_with_2h_als": 1, "full_days": 7, "als_median_delay_s": 30.0}
        res, fake = self.get("/api/traffic/queue-risk", [row])
        self.assertEqual(len(fake.calls), 1)
        self.assertNotIn("@site_id", fake.calls[0][0])
        self.assertNotIn("site_id", fake.calls[0][1])
        self.assertNotIn("day_kinds", res.json()["sites"][0])
        self.assertNotIn("longest_run_h", res.json()["sites"][0])

    def test_queue_risk_site_filter_sql_and_params(self):
        _, fake = self.get(f"/api/traffic/queue-risk?site_id={SITE}")
        self.assertEqual(len(fake.calls), 2)  # summary and hours
        for sql, params in fake.calls:
            self.assertEqual(params["site_id"], SITE)
            self.assertEqual(params["to_ts"] - params["from_ts"], timedelta(days=28))
            self.assertIn("r.site_id = @site_id", sql)
            self.assertIn("r.active", sql)
            self.assertIn("t.delay_s IS NOT NULL", sql)
            self.assertNotIn("static_ratio", sql)
            self.assertNotIn("demo_", sql)
            self.assertNotIn("Asia/", sql)
            self.assertIn("t.congestion_index >= 1.5", sql)
            self.assertIn("baseline_samples, 0) >= 302", sql)
            self.assertIn("EXTRACT(HOUR FROM t.slot_time AT TIME ZONE s.timezone)", sql)
        summary_sql = next(sql for sql, _ in fake.calls if "longest_run_h" in sql)
        hours_sql = next(sql for sql, _ in fake.calls if "GROUP BY day_kind, hour" in sql)
        self.assertIn("n >= 40 AND als_n >= 4", summary_sql)
        # weekend = Saturday, Sunday or a national holiday, from holidays.py
        self.assertIn("EXTRACT(DAYOFWEEK FROM t.slot_time AT TIME ZONE s.timezone) IN (1, 7)", hours_sql)
        self.assertIn("DATE '2026-08-17'", hours_sql)
        self.assertNotIn("DATE '2026-02-16'", hours_sql)
        # the busy rule runs in Python from these counts (busy.counts_are_busy), not in SQL
        self.assertIn("app_slow_n", hours_sql)
        self.assertIn("dep_slow_n", hours_sql)

    def test_queue_risk_site_unknown_is_404(self):
        res, fake = self.get("/api/traffic/queue-risk?site_id=nope")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(fake.calls, [])

    def test_queue_risk_site_payload_shape(self):
        summary = {"site_id": SITE, "als_pct": 31.1, "both_slow_pct": 12.1, "departure_only_pct": 0.6,
                   "days_with_2h_als": 14, "full_days": 14, "als_median_delay_s": 30.0, "longest_run_h": 6.5,
                   "days": 14}

        def hour(day_kind, h, n, als_n, app_slow_n, dep_slow_n, app_median, dep_median):
            return {"day_kind": day_kind, "hour": h, "n": n, "als_n": als_n, "app_slow_n": app_slow_n,
                    "dep_slow_n": dep_slow_n, "app_median_s": app_median, "dep_median_s": dep_median}
        hours = [
            hour("weekday", 19, 10, 6, 6, 0, 40.0, 10.0),   # approach only busy
            hour("weekday", 20, 10, 5, 5, 5, 45.0, 35.0),   # busy on both legs: not approach-only
            hour("weekday", 21, 10, 6, 6, 0, 35.0, 10.0),   # approach only busy
            hour("weekday", 22, 10, 4, 4, 0, 50.0, 10.0),   # under half slow: not busy
            hour("weekend", 17, 3, 3, 3, 0, 60.0, 10.0),    # busy but a thin sample: faded
        ]
        res, fake = self.get(f"/api/traffic/queue-risk?site_id={SITE}", [summary], hours=hours)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(set(body), {"window_days", "sites"})
        self.assertEqual(len(body["sites"]), 1)
        entry = body["sites"][0]
        self.assertEqual(set(entry), {"site_id", "tier", "als_pct", "both_slow_pct", "departure_only_pct",
                                      "days_with_2h_als", "full_days", "als_median_delay_s", "confidence",
                                      "longest_run_h", "day_kinds", "days", "ready"})
        self.assertEqual((entry["days_with_2h_als"], entry["full_days"], entry["longest_run_h"]), (14, 14, 6.5))
        self.assertEqual((entry["days"], entry["ready"]), (14, True))
        self.assertEqual([k["day_kind"] for k in entry["day_kinds"]], ["weekday", "weekend"])
        weekday, weekend = entry["day_kinds"]
        self.assertEqual([h["hour"] for h in weekday["hours"]], list(range(24)))
        self.assertEqual(len(weekend["hours"]), 24)
        by_hour = {h["hour"]: h for h in weekday["hours"]}
        self.assertEqual(set(by_hour[19]), {"hour", "n", "als_n", "als_pct", "faded", "approach_median_delay_s",
                                            "approach_only_busy"})
        self.assertEqual((by_hour[19]["n"], by_hour[19]["als_n"], by_hour[19]["als_pct"]), (10, 6, 60.0))
        self.assertEqual([by_hour[h]["approach_only_busy"] for h in (19, 20, 21, 22)], [True, False, True, False])
        self.assertFalse(by_hour[19]["faded"])
        # an hour with no reading: faded, no share, not busy
        self.assertEqual((by_hour[3]["n"], by_hour[3]["als_pct"], by_hour[3]["faded"], by_hour[3]["approach_only_busy"]),
                         (0, None, True, False))
        self.assertEqual(weekday["windows"], [
            {"start_hour": 19, "end_hour": 20, "median_delay_s": 40.0},
            {"start_hour": 21, "end_hour": 22, "median_delay_s": 35.0}])
        thin = weekend["hours"][17]
        self.assertTrue(thin["faded"])
        self.assertEqual(thin["n"], 3)
        self.assertTrue(thin["approach_only_busy"])  # same as typical-day: the flag shows, the cell fades
        # a second request is served from the cache
        again = FakeBq()
        with mock.patch("dashboard.api.bq.query", again):
            self.client.get(f"/api/traffic/queue-risk?site_id={SITE}")
        self.assertEqual(again.calls, [])

    def test_queue_risk_site_windows_wait_until_ready(self):
        def summary(days):
            return {"site_id": SITE, "als_pct": 31.1, "both_slow_pct": 12.1, "departure_only_pct": 0.6,
                    "days_with_2h_als": 6, "full_days": 6, "als_median_delay_s": 30.0, "longest_run_h": 6.5,
                    "days": days}
        hours = [{"day_kind": "weekday", "hour": 19, "n": 10, "als_n": 6, "app_slow_n": 6, "dep_slow_n": 0,
                  "app_median_s": 40.0, "dep_median_s": 10.0}]
        early, _ = self.get(f"/api/traffic/queue-risk?site_id={SITE}", [summary(6)], hours=hours)
        entry = early.json()["sites"][0]
        self.assertEqual((entry["days"], entry["ready"]), (6, False))
        for kind in entry["day_kinds"]:
            self.assertEqual(kind["windows"], [])
            self.assertFalse(any(h["approach_only_busy"] for h in kind["hours"]))
        # the share per hour is still reported; only the busy flag waits
        self.assertEqual(entry["day_kinds"][0]["hours"][19]["als_pct"], 60.0)
        cache.default.clear()
        ready, _ = self.get(f"/api/traffic/queue-risk?site_id={SITE}", [summary(7)], hours=hours)
        entry = ready.json()["sites"][0]
        self.assertTrue(entry["ready"])
        self.assertEqual(entry["day_kinds"][0]["windows"], [{"start_hour": 19, "end_hour": 20, "median_delay_s": 40.0}])

    def test_queue_risk_site_cache_is_per_site(self):
        fake = FakeBq()
        with mock.patch("dashboard.api.bq.query", fake):
            self.client.get(f"/api/traffic/queue-risk?site_id={SITE}")
            self.client.get("/api/traffic/queue-risk?site_id=34.121.03")
            self.client.get(f"/api/traffic/queue-risk?site_id={SITE}")
        self.assertEqual(len(fake.calls), 4)  # two sites x (summary + hours)

    def test_queue_risk_site_without_readings(self):
        res, _ = self.get(f"/api/traffic/queue-risk?site_id={SITE}")
        self.assertEqual(res.json(), {"window_days": 28, "sites": []})

    def test_queue_risk_site_without_als_has_zero_run(self):
        summary = {"site_id": SITE, "als_pct": 0.0, "both_slow_pct": 0.0, "departure_only_pct": 0.0,
                   "days_with_2h_als": 0, "full_days": 14, "als_median_delay_s": None, "longest_run_h": None,
                   "days": 14}
        res, _ = self.get(f"/api/traffic/queue-risk?site_id={SITE}", [summary])
        entry = res.json()["sites"][0]
        self.assertEqual(entry["longest_run_h"], 0.0)
        self.assertIsNone(entry["als_median_delay_s"])
        self.assertEqual(entry["tier"], "none")

    def test_need_login(self):
        self.client.cookies.clear()
        for path in ("latest", "series?site_id=x", "pattern?site_id=x", "typical-day?site_id=x", "queue-risk",
                     "queue-risk?site_id=x"):
            self.assertEqual(self.client.get(f"/api/traffic/{path}").status_code, 401)


if __name__ == "__main__":
    unittest.main()
