"""Unit tests for reviews_job/ (pure: no google.cloud, no network).

reviews_job/ uses bare imports (`import bq`, `import httpjson`), like places_job/ and collector/. The modules are
loaded once here with reviews_job/ first on sys.path and the other bindings saved and restored (same pattern as
tests/test_places_job.py). main() imports bq lazily, so the tests that call it patch sys.modules["bq"].
Fixtures: tests/fixtures/reviews_*.json are the 6 real legacy responses of 2026-10-08 (authors replaced by
distinct dummies). Urban site: 5+5+5 reviews, 14 distinct; toll site: 15 distinct.
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
from datetime import datetime, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOB_DIR = os.path.join(ROOT, "reviews_job")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
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
reviews, bq, main = M["reviews"], M["bq"], M["main"]

KEY = "AIzaFAKEKEY1234567890"
FETCHED = "2026-10-12T19:00:00.000000Z"
URBAN = {"site_id": "24.351.34", "place_id": "ChIJurban"}
TOLL = {"site_id": "KM57A", "place_id": "ChIJtoll"}
VARIANTS = ("newest_id", "most_relevant_id", "most_relevant_en")


def fixture(prefix, variant):
    with open(os.path.join(FIXTURES, f"reviews_{prefix}_{variant}.json")) as f:
        return json.load(f)


def fake_fetch(prefix_by_place):
    """A fetch_details stand-in answering from the fixtures, by place_id and (sort, language)."""
    def fetch(key, place_id, sort, language):
        return fixture(prefix_by_place[place_id], reviews.variant_name(sort, language)), None
    return fetch


FETCH = fake_fetch({URBAN["place_id"]: "urban", TOLL["place_id"]: "toll"})


class TestReviewKey(unittest.TestCase):
    R = {"author_name": "A", "author_url": "https://example.test/contrib/1", "time": 1788585564, "rating": 2, "text": "x"}

    def test_stable_hex(self):
        k = reviews.review_key("p", self.R)
        self.assertRegex(k, r"^[0-9a-f]{64}$")
        self.assertEqual(k, reviews.review_key("p", dict(self.R)))

    def test_ignores_rating_and_text_edits(self):
        self.assertEqual(reviews.review_key("p", self.R),
                         reviews.review_key("p", dict(self.R, rating=5, text="edited")))

    def test_changes_with_place_or_author_url(self):
        k = reviews.review_key("p", self.R)
        self.assertNotEqual(k, reviews.review_key("q", self.R))
        self.assertNotEqual(k, reviews.review_key("p", dict(self.R, author_url="https://example.test/contrib/2")))

    def test_url_form_is_sha256_of_place_and_author_url_only(self):
        want = hashlib.sha256(b"p|https://example.test/contrib/1").hexdigest()
        self.assertEqual(reviews.review_key("p", self.R), want)
        # time and author_name do not matter when the profile URL is present
        self.assertEqual(reviews.review_key("p", dict(self.R, time=1788585565, author_name="B")), want)

    def test_falls_back_to_author_name_and_time_without_url(self):
        no_url = {"author_name": "A", "time": 5}
        want = hashlib.sha256(b"p|A|5").hexdigest()
        self.assertEqual(reviews.review_key("p", no_url), want)
        self.assertEqual(reviews.review_key("p", dict(no_url, author_url="")), want)
        self.assertNotEqual(reviews.review_key("p", no_url), reviews.review_key("p", {"author_name": "B", "time": 5}))
        self.assertNotEqual(reviews.review_key("p", no_url), reviews.review_key("p", {"author_name": "A", "time": 6}))


class TestRows(unittest.TestCase):
    def test_review_row(self):
        rv = fixture("urban", "newest_id")["result"]["reviews"][1]
        row = reviews.review_row(URBAN, rv, "newest_id", FETCHED)
        self.assertEqual((row["site_id"], row["place_id"], row["rating"]), ("24.351.34", "ChIJurban", 1))
        self.assertEqual(row["published_at"], "2026-10-04T02:39:01.000000Z")
        self.assertEqual((row["language"], row["original_language"]), ("id", "id"))
        self.assertTrue(row["text"].startswith("kacau ni pelayanan"))
        self.assertEqual((row["first_seen_at"], row["last_seen_at"], row["seen_in"]), (FETCHED, FETCHED, ["newest_id"]))
        self.assertEqual(json.loads(row["raw"])["author_url"], rv["author_url"])  # raw keeps the author fields

    def test_rating_only_review_has_null_text_and_language(self):
        rv = fixture("urban", "newest_id")["result"]["reviews"][0]  # text "" and no language keys
        row = reviews.review_row(URBAN, rv, "newest_id", FETCHED)
        self.assertEqual((row["rating"], row["text"], row["language"], row["original_language"]), (3, None, None, None))

    def test_review_without_time_is_skipped(self):
        self.assertIsNone(reviews.review_row(URBAN, {"rating": 5, "author_name": "A"}, "newest_id", FETCHED))

    def test_rows_have_exactly_the_stage_columns(self):
        rv = fixture("urban", "newest_id")["result"]["reviews"][1]
        self.assertEqual(list(reviews.review_row(URBAN, rv, "newest_id", FETCHED)), [s[0] for s in bq.REVIEWS_STAGE])
        snap = reviews.snapshot_row(URBAN, "newest", "newest_id", fixture("urban", "newest_id"), "run1", FETCHED)
        self.assertEqual(list(snap), [s[0] for s in bq.SNAPSHOTS_STAGE])

    def test_snapshot_row(self):
        response = fixture("urban", "most_relevant_en")
        snap = reviews.snapshot_row(URBAN, "sample", "most_relevant_en", response, "run1", FETCHED)
        raw = snap.pop("raw")
        self.assertEqual(snap, {"run_id": "run1", "site_id": "24.351.34", "mode": "sample",
                                "variant": "most_relevant_en", "fetched_at": FETCHED,
                                "user_ratings_total": 1168, "rating": 4.4, "n_reviews": 5})
        self.assertEqual(json.loads(raw), response)  # raw = the whole response, status included
        self.assertEqual(json.loads(raw)["status"], "OK")
        self.assertNotIn(KEY, raw)

    def test_snapshot_of_a_place_without_reviews(self):
        snap = reviews.snapshot_row(URBAN, "newest", "newest_id", {"status": "OK", "result": {"rating": 4.0}}, "r", FETCHED)
        self.assertEqual((snap["n_reviews"], snap["user_ratings_total"]), (0, None))


class TestPollSite(unittest.TestCase):
    def poll(self, site, mode):
        with mock.patch.object(reviews, "fetch_details", side_effect=FETCH):
            return reviews.poll_site(KEY, site, mode, "run1", FETCHED)

    def test_variants_by_mode(self):
        self.assertEqual([reviews.variant_name(*v) for v in reviews.MODES["newest"]], ["newest_id"])
        self.assertEqual([reviews.variant_name(*v) for v in reviews.MODES["sample"]], list(VARIANTS))

    def test_dedupe_across_variants_urban(self):
        rows, snaps, calls, errors = self.poll(URBAN, "sample")
        self.assertEqual((len(rows), len(snaps), calls, errors), (14, 3, 3, []))
        self.assertEqual(len({r["review_key"] for r in rows}), 14)
        both = [r for r in rows if len(r["seen_in"]) > 1]
        self.assertEqual(len(both), 1)
        self.assertEqual(both[0]["seen_in"], ["most_relevant_id", "newest_id"])
        self.assertEqual(both[0]["published_at"], "2026-09-05T05:19:24.000000Z")  # time 1788585564

    def test_dedupe_across_variants_toll(self):
        rows, snaps, calls, errors = self.poll(TOLL, "sample")
        self.assertEqual((len(rows), len(snaps), calls), (15, 3, 3))
        self.assertTrue(all(len(r["seen_in"]) == 1 for r in rows))

    def test_newest_mode_one_call(self):
        rows, snaps, calls, errors = self.poll(URBAN, "newest")
        self.assertEqual((len(rows), len(snaps), calls), (5, 1, 1))
        self.assertEqual({r["seen_in"][0] for r in rows}, {"newest_id"})

    def test_poll_is_repeatable(self):
        a = self.poll(URBAN, "sample")[0]
        b = self.poll(URBAN, "sample")[0]
        self.assertEqual({r["review_key"] for r in a}, {r["review_key"] for r in b})

    def test_failed_call_leaves_no_rows(self):
        def fetch(key, place_id, sort, language):
            if sort == "most_relevant" and language == "en":
                return None, "HTTP 500: boom"
            return FETCH(key, place_id, sort, language)
        with mock.patch.object(reviews, "fetch_details", side_effect=fetch):
            rows, snaps, calls, errors = reviews.poll_site(KEY, URBAN, "sample", "r", FETCHED)
        self.assertEqual((len(rows), len(snaps), calls), (9, 2, 3))
        self.assertEqual(errors, ["24.351.34 most_relevant_en: HTTP 500: boom"])


class TestRequest(unittest.TestCase):
    def call(self, response=({"status": "OK", "result": {}}, None)):
        with mock.patch.object(reviews.httpjson, "request_json", return_value=response) as m:
            out = reviews.fetch_details(KEY, "ChIJurban", "newest", "id")
        return m, out

    def test_request_shape(self):
        m, out = self.call()
        method, url, headers = m.call_args.args[:3]
        self.assertEqual(method, "GET")
        self.assertTrue(url.startswith("https://maps.googleapis.com/maps/api/place/details/json?"))
        q = dict(p.split("=") for p in url.split("?")[1].split("&"))
        self.assertEqual(q["place_id"], "ChIJurban")
        self.assertEqual(q["fields"], "reviews%2Cuser_ratings_total%2Crating")
        self.assertEqual((q["reviews_sort"], q["language"], q["reviews_no_translations"]), ("newest", "id", "true"))
        self.assertEqual(out, ({"status": "OK", "result": {}}, None))  # the whole response

    def test_key_in_url_only_and_passed_for_scrubbing(self):
        m, _ = self.call()
        method, url, headers = m.call_args.args[:3]
        self.assertEqual(url.count(KEY), 1)
        self.assertIn(f"key={KEY}", url)
        self.assertNotIn(KEY, json.dumps(headers))
        self.assertEqual(m.call_args.kwargs["secret"], KEY)

    def test_non_ok_status_is_an_error_without_the_key(self):
        _, out = self.call(({"status": "REQUEST_DENIED", "error_message": f"The key {KEY} is invalid"}, None))
        self.assertEqual(out[0], None)
        self.assertEqual(out[1], "status REQUEST_DENIED: The key *** is invalid")

    def test_zero_results_is_an_error(self):
        self.assertEqual(self.call(({"status": "ZERO_RESULTS"}, None))[1][1], "status ZERO_RESULTS:")

    def test_http_error_text_never_holds_the_key(self):
        body = io.BytesIO(f"API key {KEY} not valid".encode())
        exc = urllib.error.HTTPError("https://x.test", 400, "Bad Request", {}, body)
        self.addCleanup(exc.close)
        with mock.patch.object(reviews.httpjson.urllib.request, "urlopen", side_effect=exc), \
                mock.patch.object(reviews.httpjson.time, "sleep"):
            result, err = reviews.fetch_details(KEY, "p", "newest", "id")
        self.assertIsNone(result)
        self.assertIn("API key *** not valid", err)
        self.assertNotIn(KEY, err)

    def test_url_error_text_never_holds_the_key(self):
        exc = urllib.error.URLError(f"failed for https://x.test/?key={KEY}")
        with mock.patch.object(reviews.httpjson.urllib.request, "urlopen", side_effect=exc), \
                mock.patch.object(reviews.httpjson.time, "sleep"):
            result, err = reviews.fetch_details(KEY, "p", "newest", "id")
        self.assertNotIn(KEY, err)
        self.assertIn("key=***", err)


def ddl_columns(table):
    with open(os.path.join(ROOT, "sql", "ddl.sql")) as f:
        sql = f.read()
    body = re.search(rf"CREATE TABLE IF NOT EXISTS traffic\.{table} \((.*?)\n\)\n", sql, re.S).group(1)
    cols = [m.group(1) for m in re.finditer(r"^  (\w+)\s+\S", body, re.M)]
    return cols, sql


class TestSql(unittest.TestCase):
    def test_stage_matches_ddl(self):
        self.assertEqual([s[0] for s in bq.REVIEWS_STAGE], ddl_columns("place_reviews")[0])
        self.assertEqual([s[0] for s in bq.SNAPSHOTS_STAGE], ddl_columns("place_review_snapshots")[0])

    def test_reviews_merge_shape(self):
        sql = bq.reviews_merge_sql("p.d.place_reviews", "p.d._stg")
        self.assertIn("MERGE `p.d.place_reviews` T\nUSING (\n", sql)
        self.assertIn("FROM `p.d._stg` S LEFT JOIN `p.d.place_reviews` P USING (review_key)\n) S\nON T.review_key = S.review_key\n", sql)
        source = sql.split("USING (", 1)[1].split("\n) S\n", 1)[0]
        self.assertIn("UNNEST(ARRAY_CONCAT(IFNULL(P.seen_in, []), S.seen_in))", source)
        self.assertIn("SELECT DISTINCT", source)
        matched = sql.split("\nWHEN MATCHED")[1].split("\nWHEN NOT MATCHED")[0]
        set_cols = re.findall(r"(\w+) = ", matched.split("UPDATE SET", 1)[1])
        self.assertEqual(set_cols, ["last_seen_at", "seen_in"])
        self.assertIn("GREATEST(T.last_seen_at, S.last_seen_at)", matched)
        self.assertIn("seen_in = S.merged_seen_in", matched)
        self.assertNotIn("SELECT", matched)  # BigQuery rejects a correlated subquery in UPDATE SET
        insert = sql.split("WHEN NOT MATCHED THEN INSERT")[1]
        cols = [s[0] for s in bq.REVIEWS_STAGE]
        self.assertIn(f"({', '.join(cols)})", insert)
        self.assertEqual(sql.count("PARSE_JSON(S.raw, wide_number_mode => 'round')"), 1)  # insert only
        self.assertNotIn("first_seen_at =", matched)  # kept from the first sighting

    def test_snapshots_merge_shape(self):
        sql = bq.snapshots_merge_sql("p.d.place_review_snapshots", "p.d._stg")
        on = sql.split("\nON ")[1].split("\nWHEN MATCHED")[0]
        for k in ("run_id", "site_id", "variant"):
            self.assertIn(f"T.{k} = S.{k}", on)
        self.assertIn("T.fetched_at >= TIMESTAMP_SUB(@fetched_at, INTERVAL 1 DAY)", on)
        matched = sql.split("UPDATE SET", 1)[1].split("\nWHEN NOT MATCHED")[0]
        set_cols = re.findall(r"(\w+) = ", matched)
        self.assertEqual(set_cols, ["mode", "fetched_at", "user_ratings_total", "rating", "n_reviews", "raw"])
        self.assertIn("raw = PARSE_JSON(S.raw, wide_number_mode => 'round')", matched)
        self.assertEqual(sql.count("PARSE_JSON"), 2)  # UPDATE and INSERT

    def test_only_the_snapshots_merge_uses_fetched_at_parameter(self):
        self.assertNotIn("@fetched_at", bq.reviews_merge_sql("p.d.t", "p.d.s"))
        self.assertIn("@fetched_at", bq.snapshots_merge_sql("p.d.t", "p.d.s"))

    def test_ddl_partition_cluster_and_view(self):
        cols, sql = ddl_columns("place_reviews")
        reviews_ddl = sql[sql.index("CREATE TABLE IF NOT EXISTS traffic.place_reviews"):]
        table = reviews_ddl.split("CREATE TABLE IF NOT EXISTS traffic.place_review_snapshots")[0]
        self.assertIn(")\nCLUSTER BY site_id;", table)
        self.assertNotIn("PARTITION BY", table)  # published_at spans years; MERGE by key cannot prune
        snaps = reviews_ddl.split("CREATE TABLE IF NOT EXISTS traffic.place_review_snapshots")[1].split("CREATE OR REPLACE VIEW")[0]
        self.assertIn("PARTITION BY DATE(fetched_at)\nCLUSTER BY site_id;", snaps)
        self.assertNotIn("demo_", reviews_ddl)
        self.assertIn("ALTER TABLE traffic.place_review_snapshots ADD COLUMN IF NOT EXISTS raw JSON;", snaps)
        self.assertEqual(ddl_columns("place_review_snapshots")[0][-1], "raw")

    def test_view_has_no_author_fields(self):
        sql = ddl_columns("place_reviews")[1]
        view = sql[sql.index("CREATE OR REPLACE VIEW traffic.v_place_reviews"):].split(";")[0]
        self.assertNotRegex(view, r"author|photo|raw|\*")
        cols = ddl_columns("place_reviews")[0]
        for c in cols:
            if c != "raw":
                self.assertIn(c, view)

    def test_check_unique(self):
        bq.check_unique([{"a": 1}, {"a": 2}], ("a",))
        with self.assertRaises(ValueError):
            bq.check_unique([{"a": 1}, {"a": 1}], ("a",))

    def test_poll_output_passes_check_unique(self):
        with mock.patch.object(reviews, "fetch_details", side_effect=FETCH):
            rows = reviews.poll_site(KEY, URBAN, "sample", "r", FETCHED)[0]
        bq.check_unique(rows, bq.REVIEWS_KEYS)

    def test_google_cloud_imported_lazily(self):
        self.assertNotIn("bigquery", vars(bq))

    def test_schema_repeated(self):
        with mock.patch.dict(sys.modules):  # do not leave google.cloud.* behind for the collector's import test
            try:
                import google.cloud.bigquery  # noqa: F401
            except ImportError:
                self.skipTest("google-cloud-bigquery not installed")
            schema = {f.name: f for f in bq._schema(bq.REVIEWS_STAGE)}
        self.assertEqual((schema["seen_in"].field_type, schema["seen_in"].mode), ("STRING", "REPEATED"))
        self.assertEqual(schema["published_at"].field_type, "TIMESTAMP")
        self.assertEqual(schema["rating"].field_type, "INT64")


class TestMain(unittest.TestCase):
    ENV = {"MAPS_API_KEY": KEY, "CLOUD_RUN_EXECUTION": "reviews-poller-abc12"}

    def run_main(self, argv, env=None, fetch=FETCH):
        fake_bq = mock.Mock()
        fake_bq.read_sites.return_value = [URBAN, TOLL]
        out, logs = io.StringIO(), io.StringIO()
        handler = logging.StreamHandler(logs)
        logging.getLogger().addHandler(handler)
        try:
            with mock.patch.dict(os.environ, env or self.ENV, clear=False), mock.patch.dict(sys.modules, {"bq": fake_bq}), \
                    contextlib.redirect_stdout(out), mock.patch.object(reviews, "fetch_details", side_effect=fetch):
                code = main.main(argv)
        finally:
            logging.getLogger().removeHandler(handler)
        return code, fake_bq, out.getvalue(), logs.getvalue()

    def test_default_mode_is_newest_one_call_per_site(self):
        code, fake_bq, out, logs = self.run_main([])
        self.assertEqual(code, 0)
        project, dataset, location, fetched_at, r, s = fake_bq.write_rows.call_args.args
        self.assertEqual((project, dataset, location), ("gcp-coe-sandbox", "traffic", "asia-southeast2"))
        self.assertEqual((len(r), len(s)), (10, 2))
        self.assertEqual({x["variant"] for x in s}, {"newest_id"})
        self.assertEqual({x["mode"] for x in s}, {"newest"})

    def test_sample_mode_three_variants_per_site(self):
        code, fake_bq, out, logs = self.run_main(["--mode", "sample"])
        self.assertEqual(code, 0)
        r, s = fake_bq.write_rows.call_args.args[4:]
        self.assertEqual((len(r), len(s)), (14 + 15, 6))
        self.assertEqual({x["variant"] for x in s}, set(VARIANTS))
        self.assertEqual({x["mode"] for x in s}, {"sample"})
        bq.check_unique(r, bq.REVIEWS_KEYS)

    def test_one_run_id_and_fetched_at(self):
        _, fake_bq, _, _ = self.run_main(["--mode", "sample"])
        fetched_at, r, s = fake_bq.write_rows.call_args.args[3:]
        self.assertEqual({x["run_id"] for x in s}, {"reviews-poller-abc12"})
        self.assertEqual({x["fetched_at"] for x in s} | {x["last_seen_at"] for x in r} | {x["first_seen_at"] for x in r},
                         {main.iso(fetched_at)})

    def test_unknown_mode_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_main(["--mode", "weekly"])

    def test_dry_run_writes_nothing_and_prints_no_author_data(self):
        code, fake_bq, out, logs = self.run_main(["--dry-run", "--mode", "sample"])
        self.assertEqual(code, 0)
        fake_bq.write_rows.assert_not_called()
        self.assertIn("place_reviews: 29 distinct reviews; place_review_snapshots: 6 rows", out)
        self.assertIn("sample place_reviews row:", out)
        self.assertNotIn(KEY, out + logs)
        self.assertNotIn("example.test", out + logs)  # raw (author fields) is not printed

    def test_failed_call_still_writes_the_rest_and_exits_1(self):
        def fetch(key, place_id, sort, language):
            return (None, "HTTP 500: x") if place_id == "ChIJtoll" else FETCH(key, place_id, sort, language)
        code, fake_bq, _, logs = self.run_main([], fetch=fetch)
        self.assertEqual(code, 1)
        r, s = fake_bq.write_rows.call_args.args[4:]
        self.assertEqual((len(r), len(s)), (5, 1))
        self.assertIn("KM57A newest_id: HTTP 500: x", logs)

    def test_key_never_in_output_on_failure(self):
        body = io.BytesIO(f"API key {KEY} not valid".encode())
        exc = urllib.error.HTTPError("https://x.test", 400, "Bad Request", {}, body)
        self.addCleanup(exc.close)
        with mock.patch.object(reviews.httpjson.urllib.request, "urlopen", side_effect=exc), \
                mock.patch.object(reviews.httpjson.time, "sleep"):
            code, fake_bq, out, logs = self.run_main([], fetch=reviews.fetch_details)
        self.assertEqual(code, 1)
        self.assertIn("API key *** not valid", logs)
        self.assertNotIn(KEY, out + logs)

    def test_missing_key_exits(self):
        with mock.patch.dict(os.environ, {"MAPS_API_KEY": ""}):
            with self.assertRaises(SystemExit):
                main.get_key(False)

    def test_run_id_falls_back_to_uuid(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertRegex(main.get_run_id(), r"^[0-9a-f]{32}$")

    def test_exit_code(self):
        self.assertEqual(main.exit_code(0, 0), 1)
        self.assertEqual(main.exit_code(10, 0), 0)
        self.assertEqual(main.exit_code(10, 1), 1)

    def test_iso_utc(self):
        self.assertEqual(main.iso(datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc)), FETCHED)


class TestDeployScript(unittest.TestCase):
    def test_schedules_and_secret(self):
        with open(os.path.join(ROOT, "scripts", "deploy_reviews_job.sh")) as f:
            sh = f.read()
        self.assertIn('SCHEDULE_NEWEST="0 6 * * *"', sh)
        self.assertIn('SCHEDULE_SAMPLE="0 3 * * 1"', sh)
        self.assertNotIn("6,18", sh)
        self.assertIn("SECRET_PROJECT=demogcp-terra2021", sh)
        self.assertIn('gcloud secrets add-iam-policy-binding "$SECRET"', sh)
        # overrides in the Scheduler body need run.jobs.runWithOverrides, which run.invoker lacks
        self.assertIn("--role=roles/run.jobsExecutorWithOverrides", sh)
        self.assertNotIn("roles/run.invoker", sh)


if __name__ == "__main__":
    unittest.main()
