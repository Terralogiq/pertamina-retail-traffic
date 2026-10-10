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
        sql = q.call_args_list[1].args[0]
        self.assertIn("v_place_reviews", sql)
        self.assertIn("QUALIFY ROW_NUMBER() OVER (", sql)
        self.assertIn("PARTITION BY l.review_key ORDER BY IF(l.method = 'gemini', 0, 1), l.labeled_at DESC) = 1", sql)
        for forbidden in ("r.text", "author", "raw"):  # the view has no author fields; text is only counted
            self.assertNotIn(forbidden, sql)
        counts_sql = q.call_args_list[0].args[0]
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


if __name__ == "__main__":
    unittest.main()
