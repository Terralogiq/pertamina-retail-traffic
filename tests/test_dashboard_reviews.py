"""GET /api/sites/{site_id}/review-themes with BigQuery mocked."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import cache  # noqa: E402
from dashboard.api.main import app  # noqa: E402
from dashboard.api.routers import reviews  # noqa: E402

NOW = datetime(2026, 10, 10, 3, 10, tzinfo=timezone.utc)
URL = "/api/sites/34.121.03/review-themes"


def label(published, labels, sentiment, gist="gist"):
    return {"published_at": published, "labels": labels, "sentiment": sentiment, "gist": gist}


def day(y, m, d):
    return datetime(y, m, d, 5, 0, tzinfo=timezone.utc)


COUNTS = {"n_reviews": 15, "n_text_reviews": 12}
ROWS = [
    label(day(2026, 9, 20), ["antrian", "pelayanan_petugas"], "neg", "Long queue at the pump"),
    label(day(2026, 8, 1), ["antrian"], "mixed", "Queue but friendly staff"),
    label(day(2024, 3, 5), ["antrian", "harga"], "neg", "Old queue complaint"),
    label(day(2026, 9, 25), ["kebersihan"], "pos", "Clean site"),                  # pos: not counted
    label(day(2026, 7, 2), [], "pos", "Fine"),
    label(day(2025, 10, 11), ["harga"], "neg", "Price, just inside 12 months"),
    label(day(2025, 10, 9), ["harga"], "neg", "Price, just outside"),
    label(None, ["toilet"], "neg", "Undated"),                                       # no date: older, no gist
]


def fake_query(counts=COUNTS, rows=ROWS):
    def run(sql, params=None):
        if "COUNT(*)" in sql:
            return [counts]
        if "place_review_labels" in sql:
            return rows
        raise AssertionError(sql)
    return run


class ReviewThemesTest(unittest.TestCase):
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

    def get(self, url=URL, **kw):
        with mock.patch("dashboard.api.bq.query", side_effect=fake_query(**kw)) as q:
            return self.client.get(url), q

    def test_needs_login(self):
        self.assertEqual(TestClient(app, base_url="https://testserver").get(URL).status_code, 401)

    def test_unknown_site_is_404_and_skips_bigquery(self):
        res, q = self.get("/api/sites/nope/review-themes")
        self.assertEqual(res.status_code, 404)
        q.assert_not_called()

    def test_counts_only_negative_or_mixed_split_at_twelve_months(self):
        body = self.get()[0].json()
        self.assertEqual((body["site_id"], body["n_reviews"], body["n_text_reviews"], body["n_labelled"]),
                         ("34.121.03", 15, 12, 8))
        by = {c["category"]: (c["recent"], c["older"]) for c in body["categories"]}
        # 2025-10-10 is the cutoff (NOW - 365 days): 10-11 is recent, 10-09 older; no date counts as older
        self.assertEqual(by, {"antrian": (2, 1), "pelayanan_petugas": (1, 0), "harga": (1, 2), "toilet": (0, 1)})
        self.assertNotIn("kebersihan", by)  # only in a pos review
        self.assertEqual([c["category"] for c in body["categories"]],
                         ["antrian", "harga", "pelayanan_petugas", "toilet"])  # by total, then name

    def test_gists_are_the_newest_recent_negative_or_mixed_with_a_month_and_labels(self):
        gists = self.get()[0].json()["gists"]
        self.assertEqual(gists[0], {"month": "2026-09", "labels": ["antrian", "pelayanan_petugas"],
                                    "gist": "Long queue at the pump"})
        self.assertEqual([g["month"] for g in gists], ["2026-09", "2026-08", "2025-10"])
        self.assertNotIn("2024-03", json.dumps(gists))  # older than 12 months
        self.assertNotIn("Clean site", json.dumps(gists))  # pos gists are not listed
        self.assertNotIn("Undated", json.dumps(gists))

    def test_no_labels_gives_an_empty_payload(self):
        body = self.get(rows=[])[0].json()
        self.assertEqual((body["n_labelled"], body["categories"], body["gists"]), (0, [], []))
        self.assertEqual(body["n_reviews"], 15)

    def test_response_carries_no_text_author_or_raw(self):
        rows = [dict(r, text="secret review text", author_name="Budi", raw={"author_url": "u"}) for r in ROWS]
        text = self.get(rows=rows)[0].text
        for leaked in ("secret review text", "Budi", "author", "raw"):
            self.assertNotIn(leaked, text)

    def test_queries_are_parameterised_and_prefer_gemini_over_manual(self):
        _, q = self.get()
        self.assertEqual(q.call_count, 2)
        for call in q.call_args_list:
            sql, params = call.args
            self.assertIn("site_id = @site_id", sql)
            self.assertNotIn("34.121.03", sql)
            self.assertEqual(params["site_id"], "34.121.03")
        # the two queries run concurrently: find each by its content, not its position
        sql = next(c.args[0] for c in q.call_args_list if "place_review_labels" in c.args[0])
        self.assertIn("v_place_reviews", sql)
        self.assertIn("QUALIFY ROW_NUMBER() OVER (", sql)
        self.assertIn("PARTITION BY l.review_key ORDER BY IF(l.method = 'gemini', 0, 1), l.labeled_at DESC) = 1", sql)
        for forbidden in ("r.text", "author", "raw"):  # the view has no author fields; text is only counted
            self.assertNotIn(forbidden, sql)
        counts_sql = next(c.args[0] for c in q.call_args_list if "COUNT(*)" in c.args[0])
        self.assertIn("v_place_reviews", counts_sql)
        self.assertNotIn("place_review_labels", counts_sql)

    def test_cached(self):
        with mock.patch("dashboard.api.bq.query", side_effect=fake_query()) as q:
            self.client.get(URL)
            self.client.get(URL)
        self.assertEqual(q.call_count, 2)  # one request's two queries; the second hit the cache

    def test_recent_window_constant(self):
        self.assertEqual(reviews.RECENT_DAYS, 365)
        since = NOW - timedelta(days=reviews.RECENT_DAYS)
        self.assertEqual(reviews.themes("s", COUNTS, [label(since, ["harga"], "neg")], since)["categories"],
                         [{"category": "harga", "recent": 1, "older": 0}])


SUMMARY_URL = "/api/review-themes"
SITE_IDS = ["34.121.03", "54.801.17", "74.902.22"]  # the third has no labels


def summary_rows(site_id, rows):
    return [dict(r, site_id=site_id) for r in rows]


class ReviewSummaryTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "pw"})
        patcher.start()
        self.addCleanup(patcher.stop)
        clock = mock.patch("dashboard.api.cache.utc_now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        sites = mock.patch("dashboard.api.routers.traffic.get_sites",
                           return_value=[{"site_id": s} for s in SITE_IDS])
        sites.start()
        self.addCleanup(sites.stop)
        cache.default.clear()
        self.addCleanup(cache.default.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/api/login", json={"password": "pw"})

    def summary(self, rows):
        with mock.patch("dashboard.api.bq.query", return_value=rows) as q:
            return self.client.get(SUMMARY_URL), q

    def test_needs_login(self):
        self.assertEqual(TestClient(app, base_url="https://testserver").get(SUMMARY_URL).status_code, 401)

    def test_shape_and_every_active_site_even_without_labels(self):
        res, q = self.summary(summary_rows("34.121.03", ROWS))
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(set(body), {"sites"})
        self.assertEqual([s["site_id"] for s in body["sites"]], SITE_IDS)
        for site in body["sites"]:
            self.assertEqual(set(site), {"site_id", "n_labelled", "queue_complaints", "queue_recent",
                                         "road_queue_recent", "top", "categories"})
        self.assertEqual(q.call_count, 1)  # one job for all sites
        empty = body["sites"][2]
        self.assertEqual(empty, {"site_id": "74.902.22", "n_labelled": 0, "queue_complaints": 0,
                                 "queue_recent": 0, "road_queue_recent": 0, "top": None, "categories": []})

    def test_counts_equal_the_per_site_endpoint(self):
        other = [label(day(2026, 9, 1), ["harga", "toilet"], "neg"), label(day(2025, 1, 1), ["harga"], "mixed"),
                 label(day(2026, 9, 2), ["antrian"], "pos")]
        rows = summary_rows("34.121.03", ROWS) + summary_rows("54.801.17", other)
        sites = self.summary(rows)[0].json()["sites"]
        for site_id, site_rows in (("34.121.03", ROWS), ("54.801.17", other)):
            with self.subTest(site=site_id):
                per_site = reviews.themes(site_id, COUNTS, site_rows, NOW - timedelta(days=reviews.RECENT_DAYS))
                entry = next(s for s in sites if s["site_id"] == site_id)
                self.assertEqual(entry["n_labelled"], per_site["n_labelled"])
                self.assertEqual(entry["categories"], [
                    {"category": c["category"], "count": c["recent"] + c["older"]} for c in per_site["categories"]])

    def test_counts_for_the_fixture(self):
        entry = self.summary(summary_rows("34.121.03", ROWS))[0].json()["sites"][0]
        self.assertEqual(entry["n_labelled"], 8)
        self.assertEqual(entry["queue_complaints"], 3)  # recent 2 + older 1; the pos review is not counted
        self.assertEqual(entry["categories"], [
            {"category": "antrian", "count": 3}, {"category": "harga", "count": 3},
            {"category": "pelayanan_petugas", "count": 1}, {"category": "toilet", "count": 1}])

    def test_top_lists_every_category_tied_at_the_max(self):
        entry = self.summary(summary_rows("34.121.03", ROWS))[0].json()["sites"][0]
        self.assertEqual(entry["top"], {"categories": ["antrian", "harga"], "count": 3})

    def test_top_is_one_category_without_a_tie(self):
        rows = summary_rows("54.801.17", [label(day(2026, 9, 1), ["harga"], "neg"),
                                          label(day(2026, 9, 2), ["harga", "toilet"], "mixed")])
        entry = self.summary(rows)[0].json()["sites"][1]
        self.assertEqual(entry["top"], {"categories": ["harga"], "count": 2})
        self.assertEqual(entry["queue_complaints"], 0)

    def test_only_positive_labels_give_no_top_but_count_as_labelled(self):
        rows = summary_rows("54.801.17", [label(day(2026, 9, 1), ["kebersihan"], "pos")])
        entry = self.summary(rows)[0].json()["sites"][1]
        self.assertEqual((entry["n_labelled"], entry["top"], entry["categories"], entry["queue_complaints"]),
                         (1, None, [], 0))

    def test_rows_of_unknown_sites_are_ignored(self):
        body = self.summary(summary_rows("not-a-site", ROWS))[0].json()
        self.assertEqual([s["site_id"] for s in body["sites"]], SITE_IDS)
        self.assertTrue(all(s["n_labelled"] == 0 for s in body["sites"]))

    def test_no_text_gist_or_author_and_sql_keeps_the_one_label_rule(self):
        rows = [dict(r, text="secret review text", author_name="Budi", raw={"u": 1})
                for r in summary_rows("34.121.03", ROWS)]
        res, q = self.summary(rows)
        for leaked in ("secret review text", "Budi", "author", "raw", "gist", "Long queue at the pump"):
            self.assertNotIn(leaked, res.text)
        sql = q.call_args.args[0]
        self.assertIn("PARTITION BY l.review_key ORDER BY IF(l.method = 'gemini', 0, 1), l.labeled_at DESC) = 1", sql)
        for forbidden in ("r.text", "gist", "author", "raw"):
            self.assertNotIn(forbidden, sql)

    def test_queue_recent_counts_recent_negative_or_mixed_antrian_only(self):
        entry = self.summary(summary_rows("34.121.03", ROWS))[0].json()["sites"][0]
        self.assertEqual(entry["queue_complaints"], 3)
        self.assertEqual(entry["queue_recent"], 2)  # the 2024 complaint is older; the pos review is never counted

    def test_queue_recent_cut_off_is_the_365_day_boundary(self):
        rows = summary_rows("34.121.03", [
            label(day(2025, 10, 11), ["antrian"], "neg"),    # inside
            label(day(2025, 10, 9), ["antrian"], "neg"),     # outside
            label(None, ["antrian"], "neg"),                 # undated
            label(day(2026, 9, 1), ["antrian"], "pos"),      # not negative
            label(day(2026, 9, 1), ["harga"], "neg")])       # other topic
        self.assertEqual(self.summary(rows)[0].json()["sites"][0]["queue_recent"], 1)

    def test_road_queue_recent_counts_any_sentiment_and_treats_null_as_false(self):
        def rq(published, flag, sentiment="neg"):
            return dict(label(published, ["antrian"], sentiment), road_queue=flag)
        rows = summary_rows("34.121.03", [
            rq(day(2026, 9, 1), True), rq(day(2026, 8, 1), True, "pos"), rq(day(2026, 8, 2), True, "mixed"),
            rq(day(2025, 10, 9), True),                       # older than 365 days
            rq(None, True),                                   # undated
            rq(day(2026, 9, 2), False), rq(day(2026, 9, 3), None),
            label(day(2026, 9, 4), ["antrian"], "neg")])      # a row without the column at all
        body = self.summary(rows + summary_rows("54.801.17", [rq(day(2026, 9, 5), True)]))[0].json()["sites"]
        self.assertEqual([(s["site_id"], s["road_queue_recent"]) for s in body],
                         [("34.121.03", 3), ("54.801.17", 1), ("74.902.22", 0)])

    def test_road_queue_does_not_change_the_other_counts(self):
        flagged = [dict(r, road_queue=True) for r in ROWS]
        a = self.summary(summary_rows("34.121.03", ROWS))[0].json()["sites"][0]
        cache.default.clear()
        b = self.summary(summary_rows("34.121.03", flagged))[0].json()["sites"][0]
        for k in ("n_labelled", "queue_complaints", "queue_recent", "top", "categories"):
            self.assertEqual(a[k], b[k])

    def test_sql_selects_road_queue_and_prefers_gemini_over_manual(self):
        sql = self.summary([])[1].call_args.args[0]
        self.assertIn("l.road_queue", sql)
        # the flag comes from the one chosen row per review: gemini before manual, then the latest label
        self.assertIn("ORDER BY IF(l.method = 'gemini', 0, 1), l.labeled_at DESC) = 1", sql)
        self.assertNotIn("road_queue = TRUE", sql)   # filtering before QUALIFY would let a manual row win

    def test_cached(self):
        with mock.patch("dashboard.api.bq.query", return_value=[]) as q:
            self.client.get(SUMMARY_URL)
            self.client.get(SUMMARY_URL)
        self.assertEqual(q.call_count, 1)


if __name__ == "__main__":
    unittest.main()
