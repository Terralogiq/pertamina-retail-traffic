"""Unit tests for the Gemini labeller of reviews_job/ (--mode label): stubbed Gemini client, no network, no BigQuery.

Same loading pattern as tests/test_reviews_job.py (bare imports with reviews_job/ first on sys.path, bindings saved
and restored). The stub replaces httpjson.request_json inside the gemini module, so everything above the HTTP call
(request body, parsing, validation, batching, the main() wiring) is the real code.
"""
import contextlib
import hashlib
import importlib
import io
import json
import logging
import os
import re
import sys
import unittest
import urllib.error
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOB_DIR = os.path.join(ROOT, "reviews_job")
NAMES = ("httpjson", "review_labels", "reviews", "gemini", "bq", "main")


def _load():
    saved = {n: sys.modules.pop(n) for n in NAMES if n in sys.modules}
    sys.path.insert(0, JOB_DIR)
    try:
        return {n: importlib.import_module(n) for n in NAMES}
    finally:
        sys.path.remove(JOB_DIR)
        for n in NAMES:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


M = _load()
gemini, review_labels, bq, main = M["gemini"], M["review_labels"], M["bq"], M["main"]

KEY = "AIzaFAKEGEMINIKEY1234567890"
NOW_ISO = "2026-10-10T23:30:00.000000Z"
GIST = "GISTMARKER staff were slow at the pump"
ENV = {"GEMINI_API_KEY": KEY}


def review(n, site="24.351.34"):
    return {"review_key": f"key{n:03}", "site_id": site, "text": f"TEXTMARKER{n} antrian panjang banget"}


def item(i, labels=("antrian",), sentiment="neg", gist=GIST, road_queue=False):
    return {"id": i, "labels": list(labels), "sentiment": sentiment, "gist": gist, "road_queue": road_queue}


def ok_response(items):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"items": items})}]}, "finishReason": "STOP"}]}


class StubGemini:
    """httpjson.request_json stand-in: records every call and answers from the ids in the request body."""

    def __init__(self, answer=None, fail=None):
        self.answer = answer or (lambda i: item(i))
        self.fail = fail or (lambda call_no: None)   # call number (1-based) -> an error text, or None
        self.calls = []

    def __call__(self, method, url, headers, body=None, secret=None, attempts=3, timeout=20):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body, "secret": secret,
                           "attempts": attempts, "timeout": timeout})
        err = self.fail(len(self.calls))
        if err:
            return None, err
        reviews = json.loads(body["contents"][0]["parts"][0]["text"].split("\n", 1)[1])
        return ok_response([self.answer(r["id"]) for r in reviews]), None


def patched(stub):
    return mock.patch.object(gemini.httpjson, "request_json", stub)


class TestPromptPin(unittest.TestCase):
    def test_prompt_hash_pinned_to_version(self):
        digest = hashlib.sha256(
            (gemini.SYSTEM_PROMPT + json.dumps(gemini.response_schema(), sort_keys=True)).encode()
        ).hexdigest()[:16]
        self.assertEqual((digest, gemini.PROMPT_VERSION), ("814011d8546de235", "p4"),
                         "prompt changed: bump PROMPT_VERSION")


class TestLainnyaRule(unittest.TestCase):
    def test_p2_restricts_lainnya_to_specific_remarks_and_keeps_sentiment_rules(self):
        p = gemini.SYSTEM_PROMPT
        self.assertIn("lainnya is for a specific problem or remark", p)
        self.assertIn("Never add lainnya next to other labels", p)
        self.assertIn("sentiment is judged as before", p)
        self.assertNotIn("site size, operating hours", p)   # the p1 table row that invited lainnya on praise


class TestRoadQueueRule(unittest.TestCase):
    def test_p4_rule_text_is_in_the_prompt(self):
        p = gemini.SYSTEM_PROMPT
        self.assertIn("Also return road_queue (true or false) for every review:", p)
        self.assertIn("- true only when the review says vehicles waiting for this station queue out of the site onto "
                      "the road or the roadside: the queue spills onto or blocks the main road, or drivers wait on "
                      "the road shoulder for the station.", p)
        self.assertIn("- false for queues or long waits inside the forecourt, slow or understaffed service, and "
                      "traffic jams that the review does not tie to this station's queue. A queue that is only "
                      "\"long\" is false unless it says it reaches the road.", p)

    def test_check_label_accepts_bool_and_null_and_rejects_the_rest(self):
        base = {"review_key": "k", "labels": [], "sentiment": "pos", "praise_only": True, "gist": "g"}
        for ok in (True, False, None):
            review_labels.check_label(dict(base, road_queue=ok))
        review_labels.check_label(base)   # missing key = None
        for bad in ("yes", "true", 1, 0, [], {}):
            with self.assertRaises(ValueError, msg=bad):
                review_labels.check_label(dict(base, road_queue=bad))

    def test_merge_sql_writes_road_queue(self):
        sql = review_labels.merge_sql("p.d.place_review_labels", "p.d._stg")
        self.assertIn("road_queue = S.road_queue", sql)
        self.assertIn("road_queue, method", sql)
        self.assertIn(("road_queue", "BOOL"), review_labels.STAGE)


class TestBbmKosongRule(unittest.TestCase):
    def test_p3_bbm_kosong_is_fuel_unavailable_and_early_closure_is_staff(self):
        p = gemini.SYSTEM_PROMPT
        self.assertIn("Fuel out of stock, or a grade not sold or served because it is unavailable", p)
        self.assertIn("including a subsidised grade's scheduled hours", p)
        self.assertIn("while the station still has fuel is pelayanan_petugas (a staff decision), not bbm_kosong", p)
        self.assertIn("A lane closed before the stated time while fuel is available is pelayanan_petugas", p)
        self.assertNotIn("a lane closed before the stated time, goes to bbm_kosong", p)
        self.assertNotIn("A lane closed before the stated time is bbm_kosong", p)

    def test_p3_sentiment_pos_means_no_complaint_including_informational(self):
        p = gemini.SYSTEM_PROMPT
        self.assertIn("pos: no complaint. It covers praise and also purely informational reviews", p)
        self.assertIn("neither praise nor complaint", p)


class TestRequest(unittest.TestCase):
    def setUp(self):
        self.stub = StubGemini()
        with patched(self.stub):
            gemini.label_batch(KEY, [review(1), review(2)], NOW_ISO)
        self.call = self.stub.calls[0]
        self.body = self.call["body"]

    def test_model_is_pinned_and_in_the_url(self):
        self.assertEqual(gemini.MODEL, "gemini-3.8-flash")
        self.assertEqual(gemini.MODEL_VERSION, "gemini-3.8-flash/p4")
        self.assertEqual(self.call["method"], "POST")
        self.assertEqual(self.call["url"],
                         "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent")

    def test_key_only_in_the_header_and_passed_for_scrubbing(self):
        self.assertEqual(self.call["headers"], {"x-goog-api-key": KEY})
        self.assertEqual(self.call["secret"], KEY)
        self.assertNotIn(KEY, self.call["url"])
        self.assertNotIn(KEY, json.dumps(self.body))

    def test_generation_config(self):
        cfg = self.body["generationConfig"]
        self.assertEqual(cfg["temperature"], 0)
        self.assertEqual(cfg["responseMimeType"], "application/json")

    def test_schema_enums_are_the_taxonomy_and_sentiments(self):
        schema = self.body["generationConfig"]["responseSchema"]
        props = schema["properties"]["items"]["items"]["properties"]
        self.assertEqual(props["labels"]["items"]["enum"], list(review_labels.TAXONOMY))
        self.assertEqual(len(props["labels"]["items"]["enum"]), 12)
        self.assertEqual(props["sentiment"]["enum"], ["neg", "mixed", "pos"])
        self.assertEqual(props["gist"]["type"], "STRING")
        self.assertNotIn("praise_only", props)   # derived in code, not asked of the model
        required = schema["properties"]["items"]["items"]["required"]
        self.assertEqual(sorted(required), ["gist", "id", "labels", "road_queue", "sentiment"])
        self.assertEqual(props["road_queue"], {"type": "BOOLEAN"})
        ordering = schema["properties"]["items"]["items"]["propertyOrdering"]
        self.assertEqual(ordering, ["id", "labels", "sentiment", "gist", "road_queue"])

    def test_reviews_are_sent_with_local_ids_not_review_keys(self):
        user = self.body["contents"][0]["parts"][0]["text"]
        sent = json.loads(user.split("\n", 1)[1])
        self.assertEqual([r["id"] for r in sent], [0, 1])
        self.assertEqual([r["text"] for r in sent], [review(1)["text"], review(2)["text"]])
        self.assertEqual(set(sent[0]), {"id", "text"})   # no key, no site, no rating
        self.assertNotIn("key001", json.dumps(self.body))

    def test_prompt_carries_the_taxonomy_and_the_decision_rules(self):
        prompt = self.body["systemInstruction"]["parts"][0]["text"]
        for category in review_labels.TAXONOMY:
            self.assertIn(f"| {category} |", prompt)
        for fragment in (
            "Understaffing queues", "antrian only", "Add pelayanan_petugas only when staff behaviour is attacked",
            "Barcode or MyPertamina rejection and QRIS limits go to pembayaran",
            "a lane closed before its stated time, while the station still has fuel is pelayanan_petugas",
            "Jerry-can queue-jumping or bulk buying", "fuel spilled while filling", "go to lainnya",
            "Queue spill to the road, or traffic management inside the site, goes to keamanan_lalu_lintas",
            "Labels are topics, not complaints", "toilet and kebersihan with sentiment pos",
            "mixed: praise and complaint both", "neg: the complaint dominates", "pos: no complaint",
            'A bare "Ok", "Good" or an emoji-only review gets no labels and sentiment pos',
            "no personal names, plate numbers, vehicle descriptors, phone numbers or exact dates",
        ):
            self.assertIn(fragment, prompt)

    def test_retries_and_timeout_for_one_call(self):
        self.assertEqual(self.call["attempts"], gemini.ATTEMPTS)
        self.assertGreaterEqual(self.call["attempts"], 4)
        self.assertGreaterEqual(self.call["timeout"], 60)


class TestBatching(unittest.TestCase):
    def test_25_reviews_make_three_calls_of_10_10_5(self):
        stub = StubGemini()
        reviews = [review(n) for n in range(25)]
        with patched(stub):
            rows, totals = gemini.label_reviews(KEY, reviews, NOW_ISO)
        sizes = sorted(len(json.loads(c["body"]["contents"][0]["parts"][0]["text"].split("\n", 1)[1])) for c in stub.calls)
        self.assertEqual(sizes, [5, 10, 10])
        self.assertEqual(totals["calls"], 3)
        self.assertEqual([r["review_key"] for r in rows], [r["review_key"] for r in reviews])  # order kept

    def test_ids_map_back_to_the_right_review(self):
        stub = StubGemini(answer=lambda i: item(i, labels=("toilet",) if i % 2 else ("antrian",)))
        with patched(stub):
            rows, _ = gemini.label_batch(KEY, [review(n) for n in range(4)], NOW_ISO)
        self.assertEqual([r["labels"] for r in rows], [["antrian"], ["toilet"], ["antrian"], ["toilet"]])
        self.assertEqual([r["review_key"] for r in rows], ["key000", "key001", "key002", "key003"])

    def test_answer_out_of_order_is_matched_by_id(self):
        def call(method, url, headers, body=None, **kw):
            return ok_response([item(1, labels=("toilet",)), item(0, labels=("harga",))]), None
        with mock.patch.object(gemini.httpjson, "request_json", call):
            rows, _ = gemini.label_batch(KEY, [review(0), review(1)], NOW_ISO)
        self.assertEqual([(r["review_key"], r["labels"]) for r in rows], [("key000", ["harga"]), ("key001", ["toilet"])])


class TestRows(unittest.TestCase):
    def label(self, **kw):
        stub = StubGemini(answer=lambda i: dict(item(i), **kw))
        with patched(stub):
            return gemini.label_batch(KEY, [review(0)], NOW_ISO)

    def test_row_fields(self):
        rows, counts = self.label(labels=["antrian", "pelayanan_petugas"], sentiment="mixed")
        self.assertEqual(rows, [{
            "review_key": "key000", "site_id": "24.351.34", "labels": ["antrian", "pelayanan_petugas"],
            "sentiment": "mixed", "praise_only": False, "gist": GIST, "road_queue": False, "method": "gemini",
            "model_version": "gemini-3.8-flash/p4", "labeled_at": NOW_ISO}])
        self.assertEqual(list(rows[0]), [c for c, _ in review_labels.STAGE])
        self.assertEqual(counts, {"failed_calls": 0, "invalid": 0, "missing": 0})

    def test_praise_only_is_derived_from_sentiment(self):
        for sentiment, expected in (("pos", True), ("mixed", False), ("neg", False)):
            rows, _ = self.label(sentiment=sentiment)
            self.assertIs(rows[0]["praise_only"], expected, sentiment)

    def test_praise_only_from_the_model_is_ignored(self):
        rows, _ = self.label(sentiment="neg", praise_only=True)
        self.assertIs(rows[0]["praise_only"], False)

    def test_labels_deduped_in_taxonomy_order_and_gist_on_one_line(self):
        rows, _ = self.label(labels=["toilet", "antrian", "toilet"], gist="line one\n  line   two ")
        self.assertEqual(rows[0]["labels"], ["antrian", "toilet"])
        self.assertEqual(rows[0]["gist"], "line one line two")

    def test_road_queue_is_carried_into_the_row(self):
        for flag in (True, False):
            rows, counts = self.label(road_queue=flag)
            self.assertIs(rows[0]["road_queue"], flag)
            self.assertEqual(counts["invalid"], 0)

    def test_missing_road_queue_is_stored_as_null(self):
        stub = StubGemini(answer=lambda i: {k: v for k, v in item(i).items() if k != "road_queue"})
        with patched(stub):
            rows, counts = gemini.label_batch(KEY, [review(0)], NOW_ISO)
        self.assertIsNone(rows[0]["road_queue"])
        self.assertEqual(counts["invalid"], 0)

    def test_non_bool_road_queue_is_invalid(self):
        for bad in ("yes", "true", 1, 0, [], {}):
            rows, counts = self.label(road_queue=bad)
            self.assertEqual((rows, counts["invalid"]), ([], 1), bad)

    def test_empty_labels_are_valid(self):
        rows, _ = self.label(labels=[], sentiment="pos", gist="Short praise.")
        self.assertEqual((rows[0]["labels"], rows[0]["praise_only"]), ([], True))


class TestInvalidOutput(unittest.TestCase):
    def run_items(self, items, n=3):
        def call(method, url, headers, body=None, **kw):
            return ok_response(items), None
        with mock.patch.object(gemini.httpjson, "request_json", call):
            return gemini.label_batch(KEY, [review(i) for i in range(n)], NOW_ISO)

    def test_invalid_rows_are_skipped_and_counted_valid_siblings_written(self):
        rows, counts = self.run_items([
            item(0, labels=["not_a_category"]), item(1), item(2, sentiment="neutral")], n=3)
        self.assertEqual([r["review_key"] for r in rows], ["key001"])
        self.assertEqual(counts, {"failed_calls": 0, "invalid": 2, "missing": 0})

    def test_each_kind_of_bad_field(self):
        bad = (dict(item(0), labels="antrian"), dict(item(0), labels=[1]), dict(item(0), sentiment=None),
               dict(item(0), sentiment=["pos"]), dict(item(0), gist=None), {"id": 0}, dict(item(0), labels=None))
        for b in bad:
            rows, counts = self.run_items([b], n=1)
            self.assertEqual((rows, counts["invalid"]), ([], 1), b)

    def test_missing_review_is_counted(self):
        rows, counts = self.run_items([item(0)], n=3)
        self.assertEqual([r["review_key"] for r in rows], ["key000"])
        self.assertEqual((counts["invalid"], counts["missing"]), (0, 2))

    def test_unknown_and_non_integer_ids_and_non_objects(self):
        rows, counts = self.run_items([item(0), item(7), item(-1), dict(item(1), id="1"), dict(item(1), id=True), "x"], n=2)
        self.assertEqual([r["review_key"] for r in rows], ["key000"])
        self.assertEqual((counts["invalid"], counts["missing"]), (5, 1))

    def test_repeated_id_uses_neither_answer(self):
        rows, counts = self.run_items([item(0), item(0, labels=["toilet"]), item(1)], n=2)
        self.assertEqual([r["review_key"] for r in rows], ["key001"])
        self.assertEqual((counts["invalid"], counts["missing"]), (1, 0))

    def test_failed_validation_never_reaches_the_merge_rows_of_label_reviews(self):
        stub = StubGemini(answer=lambda i: item(i) if i % 2 == 0 else item(i, labels=["x"]))
        with patched(stub):
            rows, totals = gemini.label_reviews(KEY, [review(n) for n in range(10)], NOW_ISO)
        self.assertEqual(len(rows), 5)
        self.assertEqual((totals["invalid"], totals["failed_calls"], totals["calls"]), (5, 0, 1))
        for r in rows:
            review_labels.check_label(r)   # every written row passes the loader's checks


class TestParseResponse(unittest.TestCase):
    def test_unusable_responses(self):
        cases = {
            "prompt blocked": {"promptFeedback": {"blockReason": "SAFETY"}},
            "no candidates": {},
            "finishReason MAX_TOKENS": {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{"}]}}]},
            "finishReason SAFETY": {"candidates": [{"finishReason": "SAFETY"}]},
            "output is not JSON": {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
            "output has no items list": {"candidates": [{"content": {"parts": [{"text": "[1]"}]}}]},
        }
        for reason, data in cases.items():
            self.assertEqual(gemini.parse_response(data), (None, reason))

    def test_thought_parts_are_ignored(self):
        data = {"candidates": [{"content": {"parts": [
            {"text": "thinking...", "thought": True}, {"text": json.dumps({"items": []})}]}}]}
        self.assertEqual(gemini.parse_response(data), ([], None))

    def test_failed_call_writes_nothing_for_that_batch_only(self):
        stub = StubGemini(fail=lambda n: "HTTP 400: bad request" if n == 2 else None)
        with patched(stub):
            rows, totals = gemini.label_reviews(KEY, [review(n) for n in range(30)], NOW_ISO)
        self.assertEqual((totals["calls"], totals["failed_calls"]), (3, 1))
        self.assertEqual(len(rows), 20)
        self.assertEqual(totals["reasons"], ["HTTP 400"])

    def test_error_code_drops_the_response_body(self):
        self.assertEqual(gemini.error_code("HTTP 429: quota TEXTMARKER"), "HTTP 429")
        self.assertEqual(gemini.error_code("URLError: <urlopen error>"), "URLError")


class TestRealHttpjsonPath(unittest.TestCase):
    """The stub is bypassed: urlopen is faked under the real httpjson, to see retries and scrubbing."""

    def http_error(self, code, body):
        exc = urllib.error.HTTPError("https://x.test", code, "err", {}, io.BytesIO(body.encode()))
        self.addCleanup(exc.close)
        return exc

    def test_429_and_503_are_retried_with_backoff_then_succeed(self):
        good = io.BytesIO(json.dumps(ok_response([item(0)])).encode())
        urlopen = mock.Mock(side_effect=[self.http_error(429, "slow down"), self.http_error(503, "later"), good])
        with mock.patch.object(gemini.httpjson.urllib.request, "urlopen", urlopen), \
                mock.patch.object(gemini.httpjson.time, "sleep") as sleep:
            rows, counts = gemini.label_batch(KEY, [review(0)], NOW_ISO)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])
        self.assertEqual((len(rows), counts["failed_calls"]), (1, 0))

    def test_exhausted_retries_fail_the_batch_without_key_or_body_in_the_reason(self):
        body = f"quota exceeded for key {KEY} on TEXTMARKER0"
        urlopen = mock.Mock(side_effect=[self.http_error(429, body) for _ in range(gemini.ATTEMPTS)])
        with mock.patch.object(gemini.httpjson.urllib.request, "urlopen", urlopen), \
                mock.patch.object(gemini.httpjson.time, "sleep"):
            rows, counts = gemini.label_batch(KEY, [review(0)], NOW_ISO)
        self.assertEqual(urlopen.call_count, gemini.ATTEMPTS)
        self.assertEqual((rows, counts["failed_calls"], counts["reason"]), ([], 1, "HTTP 429"))

    def test_request_goes_out_with_the_key_header(self):
        good = io.BytesIO(json.dumps(ok_response([item(0)])).encode())
        urlopen = mock.Mock(return_value=good)
        with mock.patch.object(gemini.httpjson.urllib.request, "urlopen", urlopen):
            gemini.label_batch(KEY, [review(0)], NOW_ISO)
        req = urlopen.call_args.args[0]
        self.assertEqual(req.get_header("X-goog-api-key"), KEY)
        self.assertNotIn(KEY, req.full_url)
        self.assertEqual(req.get_method(), "POST")


def ddl_columns(table):
    with open(os.path.join(ROOT, "sql", "ddl.sql")) as f:
        sql = f.read()
    body = re.search(rf"CREATE TABLE IF NOT EXISTS traffic\.{table} \((.*?)\n\)\n", sql, re.S).group(1)
    return [m.group(1) for m in re.finditer(r"^  (\w+)\s+\S", body, re.M)]


class TestSql(unittest.TestCase):
    def test_selection_sql_excludes_labelled_at_the_current_version(self):
        sql = bq.UNLABELLED_SQL.format(project="p", dataset="d")
        self.assertIn("FROM `p.d.v_place_reviews` r", sql)
        self.assertIn("r.text IS NOT NULL", sql)
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("FROM `p.d.place_review_labels` l", sql)
        self.assertIn("l.review_key = r.review_key", sql)
        self.assertIn("l.method = 'gemini'", sql)
        self.assertIn("l.model_version = @model_version", sql)   # a parameter, not a literal
        self.assertNotIn(gemini.MODEL_VERSION, sql)
        self.assertNotRegex(sql, r"(?i)\bauthor|\braw\b")

    def test_read_unlabelled_passes_the_current_model_version_as_the_parameter(self):
        with mock.patch.dict(sys.modules):   # do not leave google.cloud.* behind for the collector's import test
            try:
                import google.cloud.bigquery  # noqa: F401
            except ImportError:
                self.skipTest("google-cloud-bigquery not installed")
            client = mock.Mock()
            row = mock.Mock()
            row.items.return_value = [("review_key", "k1"), ("site_id", "s"), ("text", "t")]
            client.query.return_value.result.return_value = [row]
            with mock.patch.object(bq, "_client", return_value=client) as make_client:
                out = bq.read_unlabelled("p", "d", "asia-southeast2", gemini.MODEL_VERSION)
        make_client.assert_called_once_with("p", "asia-southeast2")
        sql = client.query.call_args.args[0]
        self.assertIn("`p.d.v_place_reviews`", sql)
        params = client.query.call_args.kwargs["job_config"].query_parameters
        self.assertEqual([(p.name, p.type_, p.value) for p in params], [("model_version", "STRING", "gemini-3.8-flash/p4")])
        self.assertEqual(out, [{"review_key": "k1", "site_id": "s", "text": "t"}])

    def test_labels_stage_matches_ddl(self):
        self.assertEqual([c for c, _ in bq.LABELS_STAGE], ddl_columns("place_review_labels"))
        self.assertEqual(bq.LABELS_KEYS, ("review_key", "method"))

    def test_merge_on_review_key_and_method(self):
        sql = review_labels.merge_sql("p.d.place_review_labels", "p.d._stg")
        self.assertIn("MERGE `p.d.place_review_labels` T\nUSING `p.d._stg` S\nON T.review_key = S.review_key AND T.method = S.method\n", sql)
        matched = sql.split("UPDATE SET", 1)[1].split("\nWHEN NOT MATCHED")[0]
        self.assertEqual(re.findall(r"(\w+) = ", matched),
                         ["site_id", "labels", "sentiment", "praise_only", "gist", "road_queue", "model_version", "labeled_at"])
        self.assertNotIn("method =", matched)   # the other method's row is never touched

    def test_write_labels_is_one_merge_with_the_labels_merge_sql(self):
        with mock.patch.object(bq, "_client", return_value="client"), mock.patch.object(bq, "_merge_table") as merge:
            bq.write_labels("p", "d", "loc", "NOW", ["row"])
        merge.assert_called_once_with("client", "p", "d", "place_review_labels", bq.LABELS_STAGE, bq.LABELS_KEYS,
                                      ["row"], "NOW", review_labels.merge_sql)

    def test_google_cloud_still_imported_lazily(self):
        self.assertNotIn("bigquery", vars(bq))


class FakeBq:
    """bq stand-in with an in-memory label table: read_unlabelled really excludes what write_labels stored."""

    def __init__(self, reviews):
        self.reviews = reviews
        self.labelled = {}
        self.reads, self.writes = [], []

    def read_unlabelled(self, project, dataset, location, model_version):
        self.reads.append((project, dataset, location, model_version))
        return [r for r in self.reviews if (r["review_key"], "gemini", model_version) not in self.labelled]

    def write_labels(self, project, dataset, location, labeled_at, rows):
        self.writes.append((project, dataset, location, labeled_at, rows))
        for r in rows:
            self.labelled[(r["review_key"], r["method"], r["model_version"])] = r

    def read_sites(self, *a):
        raise AssertionError("label mode must not read the sites")

    def write_rows(self, *a):
        raise AssertionError("label mode must not write the review tables")


class TestMainLabel(unittest.TestCase):
    def run_main(self, fake_bq, stub, argv=("--mode", "label"), env=ENV):
        out, logs = io.StringIO(), io.StringIO()
        handler = logging.StreamHandler(logs)
        root = logging.getLogger()
        level = root.level
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        try:
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.dict(sys.modules, {"bq": fake_bq}), \
                    contextlib.redirect_stdout(out), patched(stub):
                code = main.main(list(argv))
        finally:
            root.removeHandler(handler)
            root.setLevel(level)
        return code, out.getvalue(), logs.getvalue()

    def assert_no_secrets(self, text):
        self.assertNotIn(KEY, text)
        self.assertNotIn("TEXTMARKER", text)
        self.assertNotIn("GISTMARKER", text)
        self.assertNotIn("antrian panjang", text)

    def test_label_run_writes_gemini_rows_and_logs_counts_only(self):
        fake, stub = FakeBq([review(n) for n in range(23)]), StubGemini()
        code, out, logs = self.run_main(fake, stub)
        self.assertEqual(code, 0)
        self.assertEqual(len(stub.calls), 3)
        project, dataset, location, labeled_at, rows = fake.writes[0]
        self.assertEqual((project, dataset, location), ("gcp-coe-sandbox", "traffic", "asia-southeast2"))
        self.assertEqual(len(rows), 23)
        self.assertEqual({(r["method"], r["model_version"], r["labeled_at"]) for r in rows},
                         {("gemini", "gemini-3.8-flash/p4", labeled_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))})
        self.assertEqual(fake.reads, [("gcp-coe-sandbox", "traffic", "asia-southeast2", "gemini-3.8-flash/p4")])
        self.assertIn("23 text reviews without a gemini label", logs)
        self.assertIn("3 Gemini calls, 0 failed; 23 rows labelled, 0 invalid and 0 missing skipped", logs)
        self.assert_no_secrets(out + logs)

    def test_rerun_is_a_no_op_with_zero_calls(self):
        fake, stub = FakeBq([review(n) for n in range(12)]), StubGemini()
        self.assertEqual(self.run_main(fake, stub)[0], 0)
        self.assertEqual(len(stub.calls), 2)
        code, out, logs = self.run_main(fake, stub)
        self.assertEqual(code, 0)             # nothing to do is a success, not the failure alert
        self.assertEqual(len(stub.calls), 2)  # no new call
        self.assertEqual(len(fake.writes), 1)
        self.assertIn("0 text reviews without a gemini label", logs)
        self.assertIn("nothing to label, 0 Gemini calls", logs)

    def test_new_model_version_relabels_everything(self):
        fake = FakeBq([review(n) for n in range(3)])
        self.run_main(fake, StubGemini())
        stub2 = StubGemini()
        with mock.patch.object(gemini, "MODEL_VERSION", "gemini-3.8-flash/p5"):
            self.run_main(fake, stub2)
        self.assertEqual(len(stub2.calls), 1)
        self.assertEqual(len(fake.labelled), 6)   # p4 and p5 rows (the real MERGE replaces on (review_key, method))

    def test_dry_run_calls_gemini_but_writes_nothing_and_prints_counts_only(self):
        fake, stub = FakeBq([review(n) for n in range(4)]), StubGemini()
        code, out, logs = self.run_main(fake, stub, argv=("--mode", "label", "--dry-run"))
        self.assertEqual(code, 0)
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(fake.writes, [])
        self.assertIn("4 reviews selected; 1 Gemini calls (0 failed); 4 labelled, 0 invalid, 0 missing", out)
        self.assertIn("sentiment: neg 4, mixed 0, pos 0", out)
        self.assertIn("antrian 4", out)
        self.assert_no_secrets(out + logs)

    def test_invalid_rows_are_skipped_the_rest_written_exit_0(self):
        fake = FakeBq([review(n) for n in range(4)])
        stub = StubGemini(answer=lambda i: item(i, labels=["bogus"]) if i == 2 else item(i))
        code, out, logs = self.run_main(fake, stub)
        self.assertEqual(code, 0)
        self.assertEqual([r["review_key"] for r in fake.writes[0][4]], ["key000", "key001", "key003"])
        self.assertIn("3 rows labelled, 1 invalid and 0 missing skipped", logs)
        self.assert_no_secrets(out + logs)

    def test_failed_call_writes_the_other_batches_and_exits_1(self):
        fake = FakeBq([review(n) for n in range(25)])
        stub = StubGemini(fail=lambda n: f"HTTP 500: TEXTMARKER echo {KEY}" if n == 1 else None)
        code, out, logs = self.run_main(fake, stub)
        self.assertEqual(code, 1)
        self.assertEqual(len(fake.writes[0][4]), 15)
        self.assertIn("failed call reasons: HTTP 500", logs)
        self.assert_no_secrets(out + logs)
        # the failed batch is still unlabelled, so tomorrow's run picks it up
        self.assertEqual(len(fake.read_unlabelled("p", "d", "l", gemini.MODEL_VERSION)), 10)

    def test_nothing_labelled_out_of_a_non_empty_selection_exits_1(self):
        fake = FakeBq([review(0)])
        code, out, logs = self.run_main(fake, StubGemini(answer=lambda i: item(i, sentiment="x")))
        self.assertEqual(code, 1)
        self.assertEqual(fake.writes, [])
        self.assert_no_secrets(out + logs)

    def test_label_exit_code(self):
        self.assertEqual(main.label_exit_code(0, 0, 0), 0)
        self.assertEqual(main.label_exit_code(10, 0, 10), 0)
        self.assertEqual(main.label_exit_code(10, 0, 9), 0)
        self.assertEqual(main.label_exit_code(10, 1, 9), 1)
        self.assertEqual(main.label_exit_code(10, 0, 0), 1)

    def test_label_mode_needs_only_the_gemini_key(self):
        fake = FakeBq([])
        code, _, _ = self.run_main(fake, StubGemini(), env={"GEMINI_API_KEY": KEY})   # no MAPS_API_KEY
        self.assertEqual(code, 0)

    def test_missing_gemini_key_exits_naming_the_variable_only(self):
        with self.assertRaises(SystemExit) as cm:
            self.run_main(FakeBq([]), StubGemini(), env={"MAPS_API_KEY": "maps-key-value"})
        self.assertEqual(str(cm.exception), "GEMINI_API_KEY is not set")

    def test_dry_run_fetches_the_key_with_gcloud_from_the_gemini_secret_project(self):
        done = mock.Mock(returncode=0, stdout=KEY + "\n", stderr="")
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(main.subprocess, "run", return_value=done) as run:
            key = main.get_key(True, "GEMINI_API_KEY", "gemini-api-key", main.GEMINI_KEY_SECRET_PROJECT)
        self.assertEqual(key, KEY)
        cmd = run.call_args.args[0]
        self.assertIn("--secret=gemini-api-key", cmd)
        self.assertIn("--project=gcp-coe-492507", cmd)
        self.assertIn("--billing-project=gcp-coe-sandbox", cmd)

    def test_maps_get_key_default_is_unchanged(self):
        with mock.patch.dict(os.environ, {"MAPS_API_KEY": ""}):
            with self.assertRaises(SystemExit) as cm:
                main.get_key(False)
        self.assertEqual(str(cm.exception), "MAPS_API_KEY is not set")

    def test_label_mode_does_not_enter_the_places_path(self):
        with mock.patch.object(main, "run_label", return_value=0) as run_label, \
                mock.patch.object(main.reviews, "poll_site", side_effect=AssertionError("Places path")):
            self.assertEqual(main.main(["--mode", "label", "--dry-run"]), 0)
        run_label.assert_called_once_with("gcp-coe-sandbox", "traffic", "asia-southeast2", True)


class TestDeployScript(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "scripts", "deploy_reviews_job.sh")) as f:
            self.sh = f.read()

    def test_label_scheduler_runs_label_mode_after_the_newest_run(self):
        self.assertIn("SCHED_LABEL=reviews-poller-label", self.sh)
        self.assertIn('SCHEDULE_LABEL="30 6 * * *"', self.sh)
        self.assertIn('SCHEDULE_NEWEST="0 6 * * *"', self.sh)
        self.assertIn('ensure_schedule "$SCHED_LABEL" "$SCHEDULE_LABEL" label', self.sh)
        self.assertIn("--time-zone Asia/Jakarta", self.sh)

    def test_gemini_secret_is_mounted_and_granted(self):
        self.assertIn("GEMINI_SECRET_PROJECT=gcp-coe-492507", self.sh)
        self.assertIn("GEMINI_SECRET=gemini-api-key", self.sh)
        self.assertIn("GEMINI_ENV_VAR=GEMINI_API_KEY", self.sh)
        self.assertIn('--set-secrets "$ENV_VAR=$SECRET_PATH:latest,$GEMINI_ENV_VAR=$GEMINI_SECRET_PATH:latest"', self.sh)
        self.assertIn('gcloud secrets add-iam-policy-binding "$GEMINI_SECRET"', self.sh)
        self.assertIn('gcloud secrets add-iam-policy-binding "$SECRET"', self.sh)   # the maps key grant stays

    def test_project_stays_the_sandbox(self):
        self.assertIn("PROJECT=gcp-coe-sandbox", self.sh)
        self.assertIn('GC_PROJ=(--project "$PROJECT" --billing-project "$PROJECT")', self.sh)
        self.assertIn('GC_GEMINI_PROJ=(--project "$GEMINI_SECRET_PROJECT" --billing-project "$PROJECT")', self.sh)
        self.assertNotIn("--project gcp-coe-492507", self.sh)


if __name__ == "__main__":
    unittest.main()
