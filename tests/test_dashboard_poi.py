"""Places vs traffic: Spearman statistics pinned on docs/plans/poi-analysis.md, and GET /api/places/analysis with
BigQuery mocked."""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import cache, correlation  # noqa: E402
from dashboard.api.main import app  # noqa: E402
from dashboard.api.routers import poi  # noqa: E402

NOW = datetime(2026, 10, 21, 3, 10, tzinfo=timezone.utc)

# Sites in the order of the doc's per-site tables: Bandar Lampung x2, Jakarta Barat, Jakarta Selatan, Bandung,
# Surabaya, Denpasar, Balikpapan, Makassar, KM57A (last, toll).
MALLS_1KM = [52, 17, 64, 22, 63, 18, 24, 38, 29, 18]
MEAN_DELAY = [26, 32, 94, 27, 135, 10, 79, 38, 42, 7]


class CorrelationTest(unittest.TestCase):
    def test_rank_gives_ties_the_average_rank(self):
        self.assertEqual(correlation.rank([10, 20, 20, 30]), [1.0, 2.5, 2.5, 4.0])
        self.assertEqual(correlation.rank([5, 5, 5]), [2.0, 2.0, 2.0])

    def test_spearman_is_one_for_a_monotone_pair_and_none_when_a_side_is_constant(self):
        self.assertAlmostEqual(correlation.spearman([1, 2, 3, 4], [10, 200, 201, 5000]), 1.0)
        self.assertAlmostEqual(correlation.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertIsNone(correlation.spearman([1, 2, 3], [7, 7, 7]))

    def test_malls_within_1km_vs_mean_delay_matches_the_doc(self):
        result = correlation.analyse(MALLS_1KM, MEAN_DELAY)
        self.assertAlmostEqual(result["rho"], 0.657, places=3)
        self.assertAlmostEqual(result["p"], 0.045, delta=0.008)  # doc: exact p 0.045; this is a 20,000-shuffle estimate
        self.assertLess(result["ci_low"], 0.1)  # the interval reaches zero
        self.assertGreater(result["ci_high"], 0.9)
        self.assertGreaterEqual(result["loo_min"], 0.54 - 0.005)  # doc: dropping any one site keeps rho in 0.54..0.81
        self.assertLessEqual(result["loo_max"], 0.81 + 0.005)
        self.assertEqual(result["n"], 10)

    def test_dropping_the_toll_site_gives_n_9_and_the_doc_rho(self):
        result = correlation.analyse(MALLS_1KM[:-1], MEAN_DELAY[:-1])
        self.assertEqual(result["n"], 9)
        self.assertAlmostEqual(result["rho"], 0.60, places=2)  # doc: "malls vs delay +0.60"

    def test_the_estimate_is_reproducible(self):
        self.assertEqual(correlation.analyse(MALLS_1KM, MEAN_DELAY), correlation.analyse(MALLS_1KM, MEAN_DELAY))

    def test_an_unrelated_pair_is_not_flagged(self):
        result = correlation.analyse(list(range(1, 11)), [5, 10, 2, 7, 4, 9, 1, 8, 3, 6])  # rho -0.14
        self.assertGreater(result["p"], 0.5)
        self.assertLess(result["ci_low"], 0)
        self.assertGreater(result["ci_high"], 0)

    def test_too_few_sites_or_a_constant_column_gives_empty_statistics(self):
        for x, y in (([1, 2], [3, 4]), ([0, 0, 0, 0], [1, 2, 3, 4])):
            result = correlation.analyse(x, y)
            self.assertEqual(result["n"], len(x))
            self.assertTrue(all(result[k] is None for k in ("rho", "ci_low", "ci_high", "p", "loo_min", "loo_max")))


def leg_row(site_id, leg, delay, days=15, distance_m=500, peak=2.0):
    return {"site_id": site_id, "leg": leg, "distance_m": distance_m, "mean_delay_s": delay, "peak_congestion": peak,
            "days": days, "first_slot": datetime(2026, 10, 6, 17, 30, tzinfo=timezone.utc),
            "last_slot": datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)}


def hour_row(site_id, leg, hour, n=10, slow_n=8, median=60.0):
    return {"site_id": site_id, "leg": leg, "hour": hour, "n": n, "slow_n": slow_n, "median_delay_s": median}


class SiteTrafficTest(unittest.TestCase):
    def test_delay_is_per_km_so_a_1_km_leg_is_not_penalised(self):
        metrics, _ = poi.site_traffic([leg_row("a", "approach", 30, distance_m=1000)], [], "approach")
        self.assertEqual(metrics["delay"], 30)
        metrics, _ = poi.site_traffic([leg_row("a", "approach", 30, distance_m=500)], [], "approach")
        self.assertEqual(metrics["delay"], 60)

    def test_both_is_the_mean_of_the_legs_and_a_leg_switch_picks_one(self):
        legs = [leg_row("a", "approach", 10, peak=1.0), leg_row("a", "departure", 30, peak=3.0)]
        both, _ = poi.site_traffic(legs, [], "both")
        self.assertEqual((both["delay"], both["peak"]), (40, 2.0))
        departure, _ = poi.site_traffic(legs, [], "departure")
        self.assertEqual((departure["delay"], departure["peak"]), (60, 3.0))

    def test_busy_share_counts_weekday_busy_hours_per_leg(self):
        legs = [leg_row("a", "approach", 10), leg_row("a", "departure", 10)]
        hours = [hour_row("a", "approach", h) for h in range(6)]  # 6 busy hours
        hours += [hour_row("a", "approach", 6, slow_n=2), hour_row("a", "approach", 7, median=10.0)]  # not busy
        hours += [hour_row("a", "departure", 8, slow_n=5)]  # exactly half: busy
        metrics, busy_hours = poi.site_traffic(legs, hours, "both")
        self.assertEqual(busy_hours, {"approach": 6, "departure": 1})
        self.assertAlmostEqual(metrics["busy"], (6 / 24 + 1 / 24) / 2)

    def test_a_leg_with_no_weekday_reading_has_no_busy_share(self):
        metrics, busy_hours = poi.site_traffic([leg_row("a", "approach", 10)], [], "approach")
        self.assertIsNone(metrics["busy"])
        self.assertIsNone(busy_hours["approach"])


class PoiCountsTest(unittest.TestCase):
    def test_other_fuel_stations_leave_the_site_itself_out_and_unknown_radii_are_ignored(self):
        rows = [{"site_id": "a", "place_type": "gas_station", "radius_m": 500, "count": 1},
                {"site_id": "a", "place_type": "gas_station", "radius_m": 1000, "count": 3},
                {"site_id": "a", "place_type": "school", "radius_m": 1000, "count": 49},
                {"site_id": "a", "place_type": "school", "radius_m": 2000, "count": 99}]
        counts = poi.poi_counts(rows)["a"]
        self.assertEqual(counts["gas_station"], [0, 2, None])
        self.assertEqual(counts["school"], [None, 49, None])
        self.assertEqual(counts["hospital"], [None, None, None])


SITES = [{"site_id": f"s{i}", "name": f"SPBU {i}", "city": f"City {i}", "road_class": "urban"} for i in range(9)]
SITES.append({"site_id": "KM57A", "name": "KM57A", "city": "Karawang", "road_class": "toll"})
IDS = [s["site_id"] for s in SITES]


def data(days=15):
    legs = [leg_row(sid, leg, MEAN_DELAY[i] / 2, days=days) for i, sid in enumerate(IDS) for leg in ("approach", "departure")]
    hours = [hour_row(sid, "approach", 8) for sid in IDS[:3]]
    poi_rows = [{"site_id": sid, "place_type": t, "radius_m": r, "count": MALLS_1KM[i] if t == "shopping_mall" else 1 + i * (j + 1),
                 "fetched_at": datetime(2026, 10, 18, 19, 0, tzinfo=timezone.utc)}
                for i, sid in enumerate(IDS) for t, _ in poi.GROUPS for j, r in enumerate(poi.RADII)]
    return {"legs": legs, "hours": hours, "poi": poi_rows}


class PayloadTest(unittest.TestCase):
    def test_statistics_cover_six_groups_at_three_radii_in_fixed_order(self):
        out = poi.payload(data(), SITES, "delay", "both", False)
        self.assertEqual([(s["group"], s["radius_m"]) for s in out["stats"]],
                         [(g, r) for g, _ in poi.GROUPS for r in poi.RADII])
        self.assertEqual(len(out["stats"]), 18)
        self.assertTrue(all(s["n"] == 10 for s in out["stats"]))
        malls = next(s for s in out["stats"] if (s["group"], s["radius_m"]) == ("shopping_mall", 1000))
        self.assertAlmostEqual(malls["rho"], 0.657, places=3)

    def test_excluding_the_toll_site_drops_it_and_gives_n_9(self):
        out = poi.payload(data(), SITES, "delay", "both", True)
        self.assertNotIn("KM57A", [s["site_id"] for s in out["sites"]])
        self.assertTrue(all(s["n"] == 9 for s in out["stats"]))
        malls = next(s for s in out["stats"] if (s["group"], s["radius_m"]) == ("shopping_mall", 1000))
        self.assertAlmostEqual(malls["rho"], 0.60, places=2)

    def test_not_ready_below_seven_local_dates(self):
        out = poi.payload(data(days=5), SITES, "delay", "both", False)
        self.assertEqual((out["ready"], out["days"], out["ready_days"]), (False, 5, 7))
        self.assertEqual((out["sites"], out["stats"]), ([], []))

    def test_the_thinnest_site_sets_the_day_count(self):
        d = data()
        d["legs"][0]["days"] = 3  # approach leg of s0 is short, its departure leg is not
        self.assertEqual(poi.ready_days(d["legs"]), 15)
        d["legs"][1]["days"] = 3
        self.assertEqual(poi.ready_days(d["legs"]), 3)

    def test_a_site_without_a_places_run_stays_in_the_table_but_out_of_the_statistics(self):
        d = data()
        d["poi"] = [r for r in d["poi"] if r["site_id"] != "s0"]
        out = poi.payload(d, SITES, "delay", "both", False)
        self.assertIsNone(next(s for s in out["sites"] if s["site_id"] == "s0")["poi"])
        self.assertTrue(all(s["n"] == 9 for s in out["stats"]))

    def test_footer_fields(self):
        out = poi.payload(data(), SITES, "delay", "both", False)
        self.assertEqual(out["window"], {"from": "2026-10-06T17:30:00Z", "to": "2026-10-21T03:00:00Z"})
        self.assertEqual(out["places_run"], "2026-10-18T19:00:00Z")


def fake_query(d):
    def run(sql, params=None):
        if "places_aggregate" in sql:
            return d["poi"]
        if "first_slot" in sql:
            return d["legs"]
        if "slow_n" in sql:
            return d["hours"]
        raise AssertionError(sql)
    return run


class RouteTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "pw"})
        patcher.start()
        self.addCleanup(patcher.stop)
        clock = mock.patch("dashboard.api.cache.utc_now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        sites = mock.patch("dashboard.api.routers.poi.get_sites", return_value=SITES)
        sites.start()
        self.addCleanup(sites.stop)
        cache.default.clear()
        self.addCleanup(cache.default.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/api/login", json={"password": "pw"})

    def get(self, url):
        with mock.patch("dashboard.api.bq.query", side_effect=fake_query(data())) as q:
            return self.client.get(url), q

    def test_requires_a_session(self):
        anonymous = TestClient(app, base_url="https://testserver")
        self.assertEqual(anonymous.get("/api/places/analysis").status_code, 401)

    def test_is_not_read_as_a_site_id(self):
        res, _ = self.get("/api/places/analysis")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["stats"]), 18)

    def test_switches_reach_the_statistics(self):
        res, _ = self.get("/api/places/analysis?metric=peak&leg=departure&exclude_toll=true")
        body = res.json()
        self.assertEqual((body["metric"], body["leg"], body["exclude_toll"]), ("peak", "departure", True))
        self.assertEqual(len(body["sites"]), 9)

    def test_rejects_unknown_metric_or_leg(self):
        self.assertEqual(self.get("/api/places/analysis?metric=nope")[0].status_code, 400)
        self.assertEqual(self.get("/api/places/analysis?leg=nope")[0].status_code, 400)

    def test_one_set_of_bigquery_jobs_serves_every_switch(self):
        with mock.patch("dashboard.api.bq.query", side_effect=fake_query(data())) as q:
            self.client.get("/api/places/analysis?metric=delay")
            self.client.get("/api/places/analysis?metric=busy&leg=approach")
            self.client.get("/api/places/analysis?metric=delay")
        self.assertEqual(q.call_count, 3)  # legs, hours, places: once


if __name__ == "__main__":
    unittest.main()
