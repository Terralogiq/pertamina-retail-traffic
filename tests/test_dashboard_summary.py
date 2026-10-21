"""GET /api/sites/{site_id}/ai-summary with BigQuery and Gemini mocked: lookup, single-flight generation, the gate."""
import http.client
import json
import os
import sys
import threading
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import ai_summary, cache  # noqa: E402
from dashboard.api.main import app  # noqa: E402
from dashboard.api.routers import summary  # noqa: E402

with open(os.path.join(ROOT, "tests", "fixtures", "ai_summary_frozen.json")) as f:
    FROZEN = json.load(f)

NOW = datetime(2026, 10, 14, 8, 40, tzinfo=timezone.utc)      # 15:40 WIB
SLOT = datetime(2026, 10, 14, 8, 30, tzinfo=timezone.utc)
AS_OF = datetime(2026, 10, 14, 8, 30, tzinfo=timezone.utc)
URL = "/api/sites/34.121.03/ai-summary"
SITE = {"site_id": "34.121.03", "name": "SPBU TB Simatupang", "city": "Jakarta Selatan", "road_name": "Jl. TB Simatupang",
        "road_class": "urban", "timezone": "Asia/Jakarta"}
FACTS = FROZEN["facts"]["urban"]
GOOD = FROZEN["cases"][0]["sentences"]
BAD = FROZEN["cases"][4]["sentences"]   # invented time, wrong direction, wrong weekday


def gemini(sentences, error=None):
    return {"sentences": None if error else sentences, "usage": {"promptTokenCount": 1922, "candidatesTokenCount": 391,
            "thoughtsTokenCount": 40}, "model_version": "gemini-3.8-flash-001", "latency_ms": 4100, "error": error}


def stored_row():
    return {"slot_time": SLOT, "as_of": AS_OF, "generated_at": NOW, "model": ai_summary.MODEL,
            "model_version": "gemini-3.8-flash-001", "prompt_version": ai_summary.PROMPT_VERSION,
            "facts": json.dumps(FACTS), "sentences": [{"topic": s["topic"], "text": s["text"]} for s in GOOD]}


class SlotTest(unittest.TestCase):
    def test_slot_switches_at_five_and_thirty_five(self):
        at = lambda h, m: datetime(2026, 10, 14, h, m, 30, tzinfo=timezone.utc)  # noqa: E731
        self.assertEqual(summary.slot_for(at(8, 4)), datetime(2026, 10, 14, 7, 30, tzinfo=timezone.utc))
        self.assertEqual(summary.slot_for(at(8, 5)), datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(summary.slot_for(at(8, 34)), datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(summary.slot_for(at(8, 35)), SLOT)
        self.assertEqual(summary.slot_for(at(0, 2)), datetime(2026, 10, 13, 23, 30, tzinfo=timezone.utc))


class AiSummaryTest(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "pw", "GEMINI_API_KEY": "k3y"}),
                  mock.patch("dashboard.api.cache.utc_now", return_value=NOW),
                  mock.patch("dashboard.api.routers.traffic.get_sites", return_value=[SITE])):
            p.start()
            self.addCleanup(p.stop)
        cache.default.clear()
        self.addCleanup(cache.default.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/api/login", json={"password": "pw"})

    def run_get(self, lookup=(), sentences=GOOD, error=None, url=URL, facts_error=None, store_error=None):
        """GET with the lookup returning `lookup`, the facts frozen and Gemini answering `sentences`."""
        def query(sql, params=None):
            if sql == summary.LOOKUP_SQL:
                return list(lookup)
            if sql == summary.MERGE_SQL:
                if store_error:
                    raise store_error
                return []
            raise AssertionError(sql)
        facts = mock.patch.object(ai_summary, "facts_for_site", side_effect=facts_error, return_value=(FACTS, AS_OF))
        with mock.patch("dashboard.api.bq.query", side_effect=query) as q, facts as f, \
                mock.patch.object(ai_summary, "call_gemini", return_value=gemini(sentences, error)) as g:
            res = self.client.get(url)
        self.q, self.f, self.g = q, f, g
        return res

    def merges(self):
        return [c for c in self.q.call_args_list if c.args[0] == summary.MERGE_SQL]

    def test_needs_login(self):
        self.assertEqual(TestClient(app, base_url="https://testserver").get(URL).status_code, 401)

    def test_unknown_site_is_404_and_skips_bigquery(self):
        res = self.run_get(url="/api/sites/nope/ai-summary")
        self.assertEqual(res.status_code, 404)
        self.q.assert_not_called()

    def test_stored_row_is_returned_without_generating(self):
        res = self.run_get(lookup=[stored_row()])
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["site_id"], "34.121.03")
        s = body["summary"]
        self.assertEqual((s["slot_time"], s["as_of"], s["model"], s["prompt_version"]),
                         ("2026-10-14T08:30:00Z", "2026-10-14T08:30:00Z", "gemini-3.8-flash", "s5"))
        self.assertEqual([x["topic"] for x in s["sentences"]], [x["topic"] for x in GOOD])
        self.assertEqual(s["facts"], FACTS)
        self.assertEqual(set(s["sources"]), {"traffic", "weather", "places", "review_themes"})
        self.f.assert_not_called()
        self.g.assert_not_called()
        self.assertEqual(self.merges(), [])

    def test_lookup_is_keyed_on_site_slot_model_and_prompt(self):
        self.run_get(lookup=[stored_row()])
        sql, params = self.q.call_args.args
        self.assertEqual(params, {"site_id": "34.121.03", "slot_time": SLOT, "model": "gemini-3.8-flash",
                                  "prompt_version": "s5"})
        self.assertIn("slot_time = @slot_time", sql)   # the partition column
        self.assertIn("validation_ok", sql)
        self.assertNotIn("34.121.03", sql)

    def test_miss_generates_once_stores_and_returns(self):
        res = self.run_get()
        s = res.json()["summary"]
        self.assertEqual([x["text"] for x in s["sentences"]], [x["text"] for x in GOOD])
        self.assertEqual(set(s["sentences"][0]), {"topic", "text"})   # validator details are stored, not sent
        self.assertEqual(s["model_version"], "gemini-3.8-flash-001")
        self.assertEqual(self.f.call_args.args, (SITE, NOW))
        self.assertEqual(self.g.call_args.args, ("k3y", FACTS))
        [merge] = self.merges()
        params = merge.args[1]
        self.assertEqual((params["site_id"], params["slot_time"], params["as_of"], params["prompt_version"]),
                         ("34.121.03", SLOT, AS_OF, "s5"))
        self.assertIs(params["validation_ok"], True)
        self.assertEqual((params["input_tokens"], params["output_tokens"], params["latency_ms"]), (1922, 431, 4100))
        self.assertEqual(json.loads(params["facts"]), FACTS)
        stored = json.loads(params["sentences"])
        self.assertEqual(len(stored), len(GOOD))
        self.assertTrue(all(x["ok"] and x["problems"] == [] for x in stored))
        self.assertIn({"number": "25", "match": "exact"}, stored[0]["number_matches"])

    def test_rejected_answer_is_not_stored_and_gives_no_summary(self):
        res = self.run_get(sentences=BAD)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"site_id": "34.121.03", "summary": None})
        self.assertEqual(self.merges(), [])

    def test_gemini_failure_gives_no_summary(self):
        res = self.run_get(error="HTTP 429")
        self.assertEqual((res.status_code, res.json()["summary"]), (200, None))
        self.assertEqual(self.merges(), [])

    def test_gemini_call_raising_gives_no_summary(self):
        with mock.patch("dashboard.api.bq.query", return_value=[]) as q, \
                mock.patch.object(ai_summary, "facts_for_site", return_value=(FACTS, AS_OF)), \
                mock.patch.object(ai_summary, "call_gemini", side_effect=http.client.IncompleteRead(b"")):
            res = self.client.get(URL)
        self.assertEqual((res.status_code, res.json()["summary"]), (200, None))
        self.assertEqual([c for c in q.call_args_list if c.args[0] == summary.MERGE_SQL], [])

    def test_a_generation_that_crosses_the_boundary_stays_in_its_slot(self):
        clock = [datetime(2026, 10, 14, 8, 34, tzinfo=timezone.utc)]   # slot 08:00
        lookups, merges = [], []

        def query(sql, params=None):
            if sql == summary.LOOKUP_SQL:
                lookups.append(params["slot_time"])
                clock[0] = datetime(2026, 10, 14, 8, 36, tzinfo=timezone.utc)   # the compute finishes after :35
                return []
            merges.append(params["slot_time"])
            return []
        with mock.patch("dashboard.api.cache.utc_now", side_effect=lambda: clock[0]), \
                mock.patch("dashboard.api.bq.query", side_effect=query), \
                mock.patch.object(ai_summary, "facts_for_site", return_value=(FACTS, AS_OF)), \
                mock.patch.object(ai_summary, "call_gemini", return_value=gemini(GOOD)):
            first = self.client.get(URL).json()["summary"]
            second = self.client.get(URL).json()["summary"]   # 08:36: slot 08:30, not the 08:00 entry
        early = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(lookups, [early, SLOT])
        self.assertEqual(merges, [early, SLOT])
        self.assertEqual((first["slot_time"], second["slot_time"]), ("2026-10-14T08:00:00Z", "2026-10-14T08:30:00Z"))

    def test_missing_key_gives_no_summary_and_no_call(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            res = self.run_get()
        self.assertIsNone(res.json()["summary"])
        self.f.assert_not_called()
        self.g.assert_not_called()

    def test_facts_or_lookup_failure_gives_no_summary(self):
        self.assertIsNone(self.run_get(facts_error=RuntimeError("bq down")).json()["summary"])
        self.g.assert_not_called()
        cache.default.clear()
        with mock.patch("dashboard.api.bq.query", side_effect=RuntimeError("Not found: Table ai_summaries")), \
                mock.patch.object(ai_summary, "call_gemini") as g:
            res = self.client.get(URL)
        self.assertEqual((res.status_code, res.json()["summary"]), (200, None))
        g.assert_not_called()

    def test_store_failure_still_shows_the_validated_summary(self):
        res = self.run_get(store_error=RuntimeError("Access Denied"))
        self.assertEqual(len(res.json()["summary"]["sentences"]), len(GOOD))

    def test_result_is_cached_for_the_slot_including_none(self):
        self.run_get(sentences=BAD)
        self.run_get(sentences=GOOD)
        self.q.assert_not_called()   # the second view of the slot reuses the first answer, null included
        self.g.assert_not_called()

    def test_concurrent_first_views_share_one_generation(self):
        calls = []
        release = threading.Event()

        def slow_generate(site, slot, now):
            calls.append(slot)
            release.wait(5)
            return None

        results = []
        with mock.patch("dashboard.api.bq.query", return_value=[]), \
                mock.patch.object(summary, "generate", side_effect=slow_generate):
            threads = [threading.Thread(target=lambda: results.append(summary.ai_summary_for_site("34.121.03")))
                       for _ in range(3)]
            for t in threads:
                t.start()
            time.sleep(0.2)
            release.set()
            for t in threads:
                t.join(5)
        self.assertEqual(len(calls), 1)
        self.assertEqual(results, [{"site_id": "34.121.03", "summary": None}] * 3)


class MergeSqlTest(unittest.TestCase):
    def test_merge_key_and_partition_filter(self):
        sql = summary.MERGE_SQL
        self.assertIn("ON t.slot_time = @slot_time AND t.site_id = s.site_id AND t.model = s.model "
                      "AND t.prompt_version = s.prompt_version", sql)
        self.assertIn("PARSE_JSON(@facts)", sql)
        self.assertIn("`gcp-coe-sandbox.traffic.ai_summaries`", sql)


class FactsForSiteTest(unittest.TestCase):
    def test_seven_queries_in_one_parallel_call_and_one_key_per_topic(self):
        local = datetime(2026, 10, 14, 15, 0)
        slot_rows = [{"leg": "approach", "slot_time": AS_OF, "local_dt": local, "delay_s": 12.0,
                      "baseline_samples": 336, "slow": 0}]
        weather = [{"slot_time": AS_OF, "local_dt": local, "temperature_c": None, "rain": False}]
        answers = [slot_rows, weather, [{"rating": 4.4, "user_rating_count": 1656}],
                   [{"radius_m": 1000, "brand": "Shell", "distance_m": 300.0}],
                   [{"place_type": "cafe", "count": 59}],
                   [{"sentiment": "neg", "label": "antrian"}, {"sentiment": "pos", "label": "toilet"}],
                   [{"n_reviews": 15, "n_text": 12}]]
        with mock.patch("dashboard.api.bq.query_all", return_value=answers) as qa:
            facts, as_of = ai_summary.facts_for_site(SITE, NOW)
        jobs = qa.call_args.args
        self.assertEqual(len(jobs), 7)
        self.assertEqual(jobs[0][1]["gate_s"], 20)
        self.assertEqual(jobs[1][1]["tz"], "Asia/Jakarta")
        for sql, params in jobs:
            self.assertEqual(params["site_id"], "34.121.03")
            self.assertNotIn("34.121.03", sql)
            for forbidden in ("l.gist", "author", "raw"):
                self.assertNotIn(forbidden, sql)
        self.assertEqual(as_of, AS_OF)
        self.assertEqual(set(facts), {"site", "traffic", "weather", "places", "review_themes"})
        self.assertEqual(facts["weather"]["today_temp_min_c"], None)   # a null temperature is skipped, not a crash
        self.assertEqual(facts["places"]["google_rating"], 4.4)
        self.assertEqual(facts["review_themes"]["complaint_theme_counts"], {"antrian": 1})
        self.assertEqual(facts["review_themes"]["reviews_with_text"], 12)


if __name__ == "__main__":
    unittest.main()
