"""Unit tests for places_job/ (pure: no google.cloud, no network).

places_job/ uses bare imports (`import bq`, `import places`), like collector/, and the collector tests
bind the same names in sys.modules. The modules are therefore loaded once here with places_job/ first
on sys.path and the other bindings saved and restored, so neither side sees the other's modules.
main() imports bq lazily, so the tests that call it patch sys.modules["bq"].
"""
import contextlib
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
JOB_DIR = os.path.join(ROOT, "places_job")
NAMES = ("httpjson", "places", "bq", "main")


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
places, bq, main = M["places"], M["bq"], M["main"]

KEY = "AIzaFAKEKEY1234567890"
FETCHED = "2026-10-12T19:00:00.000000Z"

DETAILS = {
    "id": "ChIJsite", "displayName": {"text": "SPBU Pertamina 34.121.03", "languageCode": "id"},
    "rating": 4.3, "userRatingCount": 120, "businessStatus": "OPERATIONAL", "primaryType": "gas_station",
    "location": {"latitude": -6.2, "longitude": 106.8}, "utcOffsetMinutes": 420,
    "regularOpeningHours": {"openNow": True, "weekdayDescriptions": ["Senin: 24 jam", "Selasa: 24 jam"]},
    "currentOpeningHours": {"openNow": False},
    "reviews": [
        {"rating": 5, "originalText": {"text": "Bagus", "languageCode": "id"}, "text": {"text": "Good", "languageCode": "en"},
         "publishTime": "2025-03-01T10:20:30.123456789Z", "authorAttribution": {"displayName": "Budi"}},
        {"rating": 2, "text": {"text": "Slow", "languageCode": "en"}, "publishTime": "2025-02-01T00:00:00Z"},
    ],
}
NEARBY = {"places": [
    {"id": "ChIJsite", "displayName": {"text": "SPBU Pertamina 34.121.03"}, "location": {"latitude": -6.2, "longitude": 106.8},
     "primaryType": "gas_station", "rating": 4.3, "userRatingCount": 120, "businessStatus": "OPERATIONAL"},
    {"id": "ChIJshell", "displayName": {"text": "Shell Simatupang"}, "location": {"latitude": -6.2, "longitude": 106.809}},
    {"id": "ChIJshell", "displayName": {"text": "dup"}},
    {"displayName": {"text": "no id"}},
]}


def fake_fetchers(details=(DETAILS, None), nearby=(NEARBY, None), aggregate=({"count": "7"}, None)):
    return (mock.patch.object(places, "fetch_details", return_value=details),
            mock.patch.object(places, "fetch_nearby", return_value=nearby),
            mock.patch.object(places, "fetch_aggregate", return_value=aggregate))


@contextlib.contextmanager
def patched(**kw):
    with contextlib.ExitStack() as st:
        for p in fake_fetchers(**kw):
            st.enter_context(p)
        yield


class TestHelpers(unittest.TestCase):
    def test_not_collector_modules(self):
        self.assertTrue(os.path.samefile(os.path.dirname(bq.__file__), JOB_DIR))
        self.assertTrue(os.path.samefile(os.path.dirname(main.__file__), JOB_DIR))
        self.assertIsNot(places.httpjson, sys.modules.get("httpjson"))

    def test_brand_of(self):
        for name, brand in (("SPBU Pertamina - Tirtayasa", "Pertamina"), ("24.351-34", "Pertamina"),
                            ("Shell Simatupang", "Shell"), ("BP-AKR Daan Mogot", "BP"), ("Vivo Energy", "Vivo"),
                            ("Pertamini Pak Eko", "other"), (None, "other")):
            with self.subTest(name=name):
                self.assertEqual(places.brand_of(name), brand)

    def test_ts_cuts_nanoseconds(self):
        self.assertEqual(places.ts("2025-03-01T10:20:30.123456789Z"), "2025-03-01T10:20:30.123456Z")
        self.assertEqual(places.ts("2025-03-01T10:20:30.5Z"), "2025-03-01T10:20:30.500000Z")
        self.assertEqual(places.ts("2025-03-01T10:20:30Z"), "2025-03-01T10:20:30Z")
        self.assertIsNone(places.ts("yesterday"))
        self.assertIsNone(places.ts(None))

    def test_haversine(self):
        self.assertEqual(places.haversine_m(-6.2, 106.8, -6.2, 106.8), 0)
        # 0.009 degrees of longitude at 6.2 S is about 995 m
        self.assertAlmostEqual(places.haversine_m(-6.2, 106.8, -6.2, 106.809), 995, delta=5)


class TestRows(unittest.TestCase):
    def test_details_row(self):
        row = places.details_row("run1", "34.121.03", FETCHED, DETAILS)
        self.assertEqual((row["run_id"], row["site_id"], row["fetched_at"], row["place_id"]),
                         ("run1", "34.121.03", FETCHED, "ChIJsite"))
        self.assertEqual((row["rating"], row["user_rating_count"], row["utc_offset_minutes"]), (4.3, 120, 420))
        self.assertIs(row["open_now"], False)  # currentOpeningHours wins over regular
        self.assertEqual(row["weekday_descriptions"], ["Senin: 24 jam", "Selasa: 24 jam"])
        self.assertEqual(row["reviews"][0], {
            "rating": 5, "text": "Bagus", "language": "id",
            "publish_time": "2025-03-01T10:20:30.123456Z", "author_name": "Budi"})
        self.assertEqual(row["reviews"][1]["text"], "Slow")      # falls back to translated text
        self.assertEqual(row["reviews"][1]["language"], "en")
        self.assertIsNone(row["reviews"][1]["author_name"])
        self.assertEqual(json.loads(row["raw"]), DETAILS)

    def test_details_row_sparse(self):
        row = places.details_row("r", "s", FETCHED, {"id": "x"})
        self.assertEqual(row["reviews"], [])
        self.assertEqual(row["weekday_descriptions"], [])
        self.assertIsNone(row["rating"])
        self.assertIsNone(row["open_now"])

    def test_nearby_rows(self):
        rows = places.nearby_rows("run1", "s1", FETCHED, 1000, -6.2, 106.8, NEARBY)
        self.assertEqual([r["place_id"] for r in rows], ["ChIJsite", "ChIJshell"])  # dup and id-less dropped
        site, shell = rows
        self.assertEqual((site["rank"], site["distance_m"], site["brand"]), (1, 0, "Pertamina"))
        self.assertEqual((shell["rank"], shell["brand"], shell["radius_m"]), (2, "Shell", 1000))
        self.assertAlmostEqual(shell["distance_m"], 995, delta=5)
        self.assertIsNone(shell["rating"])
        self.assertEqual(json.loads(shell["raw"])["id"], "ChIJshell")
        bq.check_unique(rows, bq.NEARBY_KEYS)

    def test_aggregate_row(self):
        self.assertEqual(places.aggregate_row("r", "s", FETCHED, "cafe", 500, {"count": "12"})["count"], 12)
        self.assertEqual(places.aggregate_row("r", "s", FETCHED, "cafe", 500, {})["count"], 0)

    def test_rows_have_exactly_the_stage_columns(self):
        d = places.details_row("r", "s", FETCHED, DETAILS)
        n = places.nearby_rows("r", "s", FETCHED, 1000, -6.2, 106.8, NEARBY)[0]
        a = places.aggregate_row("r", "s", FETCHED, "cafe", 500, {"count": "1"})
        for row, stage in ((d, bq.DETAILS_STAGE), (n, bq.NEARBY_STAGE), (a, bq.AGGREGATE_STAGE)):
            self.assertEqual(set(row), {s[0] for s in stage})
        self.assertEqual(set(d["reviews"][0]), {f[0] for f in bq.REVIEW_FIELDS})


class TestRequests(unittest.TestCase):
    def call(self, fn, *args):
        with mock.patch.object(places.httpjson, "request_json", return_value=({}, None)) as m:
            fn(KEY, *args)
        return m.call_args

    def test_key_only_in_header_and_scrubbed(self):
        for fn, args in ((places.fetch_details, ("ChIJsite",)), (places.fetch_nearby, (-6.2, 106.8, 1000)),
                         (places.fetch_aggregate, ("ChIJsite", "cafe", 500))):
            with self.subTest(fn=fn.__name__):
                c = self.call(fn, *args)
                method, url, headers = c.args[:3]
                self.assertNotIn(KEY, url)
                self.assertNotIn(KEY, json.dumps(c.args[3:]))
                self.assertEqual(headers["X-Goog-Api-Key"], KEY)
                self.assertEqual(c.kwargs["secret"], KEY)

    def test_details_request(self):
        method, url, headers = self.call(places.fetch_details, "ChIJsite").args
        self.assertEqual(method, "GET")
        self.assertTrue(url.startswith("https://places.googleapis.com/v1/places/ChIJsite?"))
        self.assertEqual(headers["X-Goog-FieldMask"].split(","), places.DETAILS_FIELDS)
        self.assertEqual(len(places.DETAILS_FIELDS), 36)

    def test_nearby_request(self):
        method, url, headers, body = self.call(places.fetch_nearby, -6.2, 106.8, 3000).args
        self.assertEqual(method, "POST")
        self.assertEqual(body["includedTypes"], ["gas_station"])
        self.assertEqual((body["maxResultCount"], body["rankPreference"]), (20, "DISTANCE"))
        self.assertEqual(body["locationRestriction"]["circle"]["radius"], 3000.0)
        self.assertIn("places.location", headers["X-Goog-FieldMask"].split(","))

    def test_aggregate_request(self):
        method, url, headers, body = self.call(places.fetch_aggregate, "ChIJsite", "cafe", 500).args
        self.assertEqual(url, "https://areainsights.googleapis.com/v1:computeInsights")
        f = body["filter"]
        self.assertEqual(f["locationFilter"]["circle"], {"place": "places/ChIJsite", "radius": 500})
        self.assertEqual(f["typeFilter"]["includedTypes"], ["cafe"])
        self.assertEqual(body["insights"], ["INSIGHT_COUNT"])

    def test_call_matrix(self):
        self.assertEqual(places.NEARBY_RADII, [1000, 3000])
        self.assertEqual(places.AGG_RADII, [500, 1000, 3000])
        self.assertEqual(len(places.AGG_TYPES), 15)


class TestProfileSite(unittest.TestCase):
    SITE = {"site_id": "34.121.03", "place_id": "ChIJsite"}

    def test_full_site(self):
        with patched():
            d, n, a, calls, errors = places.profile_site(KEY, self.SITE, "run1", FETCHED)
        self.assertEqual((len(d), len(n), len(a), calls, errors), (1, 4, 45, 48, []))
        self.assertEqual({r["radius_m"] for r in n}, {1000, 3000})
        bq.check_unique(a, bq.AGGREGATE_KEYS)
        bq.check_unique(n, bq.NEARBY_KEYS)

    def test_details_failure_skips_nearby_but_not_aggregate(self):
        with patched(details=(None, "HTTP 403: denied")):
            d, n, a, calls, errors = places.profile_site(KEY, self.SITE, "run1", FETCHED)
        self.assertEqual((len(d), len(n), len(a), calls), (0, 0, 45, 46))
        self.assertEqual(errors, ["details 34.121.03: HTTP 403: denied"])

    def test_failed_calls_leave_no_row(self):
        with patched(aggregate=(None, "HTTP 400: bad type")):
            d, n, a, calls, errors = places.profile_site(KEY, self.SITE, "run1", FETCHED)
        self.assertEqual((len(d), len(a), calls, len(errors)), (1, 0, 48, 45))

    def test_no_location_skips_nearby(self):
        with patched(details=({"id": "ChIJsite"}, None)):
            d, n, a, calls, errors = places.profile_site(KEY, self.SITE, "run1", FETCHED)
        self.assertEqual((len(d), len(n), calls, len(errors)), (1, 0, 46, 1))


def ddl_columns(table):
    with open(os.path.join(ROOT, "sql", "ddl.sql")) as f:
        sql = f.read()
    body = re.search(rf"CREATE TABLE IF NOT EXISTS traffic\.{table} \((.*?)\n\)\n", sql, re.S).group(1)
    cols = [m.group(1) for m in re.finditer(r"^  (\w+)\s+\S", body, re.M)]
    return cols, sql


class TestMergeSql(unittest.TestCase):
    CASES = (("places_details", bq.DETAILS_STAGE, bq.DETAILS_KEYS),
             ("places_nearby", bq.NEARBY_STAGE, bq.NEARBY_KEYS),
             ("places_aggregate", bq.AGGREGATE_STAGE, bq.AGGREGATE_KEYS))

    def sql(self, table, stage, keys):
        return bq.merge_sql(f"p.d.{table}", "p.d._stg", stage, keys)

    def test_on_clause_keys_start_with_run_id_and_prune(self):
        for table, stage, keys in self.CASES:
            with self.subTest(table=table):
                self.assertEqual(keys[0], "run_id")
                on = self.sql(table, stage, keys).split("\nON ")[1].split("\nWHEN MATCHED")[0]
                for k in keys:
                    self.assertIn(f"T.{k} = S.{k}", on)
                self.assertIn("T.fetched_at >= TIMESTAMP_SUB(@fetched_at, INTERVAL 1 DAY)", on)

    def test_update_excludes_keys_and_parses_raw(self):
        for table, stage, keys in self.CASES:
            with self.subTest(table=table):
                sql = self.sql(table, stage, keys)
                matched = sql.split("\nWHEN MATCHED")[1].split("\nWHEN NOT MATCHED")[0]
                set_cols = re.findall(r"(\w+) = ", matched.split("UPDATE SET", 1)[1])
                for k in keys:
                    self.assertNotIn(k, set_cols)
                self.assertIn("fetched_at", set_cols)
                self.assertIn("raw = PARSE_JSON(S.raw, wide_number_mode => 'round')", matched)
                self.assertEqual(sql.count("PARSE_JSON"), 2)  # UPDATE and INSERT

    def test_stage_matches_ddl(self):
        for table, stage, _ in self.CASES:
            with self.subTest(table=table):
                self.assertEqual([s[0] for s in stage], ddl_columns(table)[0])

    def test_ddl_partition_and_cluster(self):
        sql = ddl_columns("places_details")[1]
        places_ddl = sql[sql.index("CREATE TABLE IF NOT EXISTS traffic.places_details"):sql.index("-- Review tables")]
        self.assertEqual(places_ddl.count("PARTITION BY DATE(fetched_at)\nCLUSTER BY site_id;"), 3)
        self.assertNotIn("demo_", places_ddl)

    def test_check_unique(self):
        bq.check_unique([{"a": 1}, {"a": 2}], ("a",))
        with self.assertRaises(ValueError):
            bq.check_unique([{"a": 1}, {"a": 1}], ("a",))

    def test_google_cloud_imported_lazily(self):
        self.assertNotIn("bigquery", vars(bq))

    def test_schema_nested_and_repeated(self):
        with mock.patch.dict(sys.modules):  # do not leave google.cloud.* behind for the collector's import test
            try:
                import google.cloud.bigquery  # noqa: F401
            except ImportError:
                self.skipTest("google-cloud-bigquery not installed")
            schema = {f.name: f for f in bq._schema(bq.DETAILS_STAGE)}
        self.assertEqual([f for f in schema], [s[0] for s in bq.DETAILS_STAGE])
        reviews = schema["reviews"]
        self.assertEqual((reviews.field_type, reviews.mode), ("RECORD", "REPEATED"))
        self.assertEqual([(f.name, f.field_type, f.mode) for f in reviews.fields],
                         [(n, t, "NULLABLE") for n, t in bq.REVIEW_FIELDS])
        self.assertEqual((schema["weekday_descriptions"].field_type, schema["weekday_descriptions"].mode),
                         ("STRING", "REPEATED"))
        self.assertEqual((schema["rating"].field_type, schema["rating"].mode), ("FLOAT64", "NULLABLE"))
        self.assertEqual(schema["fetched_at"].field_type, "TIMESTAMP")


class TestMain(unittest.TestCase):
    def run_main(self, argv, env, fetchers=None):
        fake_bq = mock.Mock()
        fake_bq.read_sites.return_value = [{"site_id": "s1", "place_id": "ChIJ1"}, {"site_id": "s2", "place_id": "ChIJ2"}]
        out, logs = io.StringIO(), io.StringIO()
        handler = logging.StreamHandler(logs)
        logging.getLogger().addHandler(handler)
        try:
            with mock.patch.dict(os.environ, env, clear=False), mock.patch.dict(sys.modules, {"bq": fake_bq}), \
                    contextlib.redirect_stdout(out), (fetchers or patched()):
                code = main.main(argv)
        finally:
            logging.getLogger().removeHandler(handler)
        return code, fake_bq, out.getvalue(), logs.getvalue()

    ENV = {"MAPS_API_KEY": KEY, "CLOUD_RUN_EXECUTION": "places-profiler-abc12"}

    def test_run_writes_once_with_one_run_id_and_fetched_at(self):
        code, fake_bq, out, logs = self.run_main([], self.ENV)
        self.assertEqual(code, 0)
        fake_bq.write_rows.assert_called_once()
        project, dataset, location, fetched_at, d, n, a = fake_bq.write_rows.call_args.args
        self.assertEqual((project, dataset, location), ("gcp-coe-sandbox", "traffic", "asia-southeast2"))
        self.assertEqual((len(d), len(n), len(a)), (2, 8, 90))
        rows = d + n + a
        self.assertEqual({r["run_id"] for r in rows}, {"places-profiler-abc12"})
        self.assertEqual(len({r["fetched_at"] for r in rows}), 1)
        self.assertEqual(rows[0]["fetched_at"], main.iso(fetched_at))
        self.assertNotIn(KEY, out + logs)

    def test_new_execution_new_run_id(self):
        a = self.run_main([], self.ENV)[1].write_rows.call_args.args[4][0]["run_id"]
        b = self.run_main([], {**self.ENV, "CLOUD_RUN_EXECUTION": "places-profiler-def34"})[1].write_rows.call_args.args[4][0]["run_id"]
        self.assertNotEqual(a, b)

    def test_run_id_falls_back_to_uuid(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertRegex(main.get_run_id(), r"^[0-9a-f]{32}$")

    def test_dry_run_writes_nothing_and_prints_samples(self):
        code, fake_bq, out, logs = self.run_main(["--dry-run"], self.ENV)
        self.assertEqual(code, 0)
        fake_bq.write_rows.assert_not_called()
        self.assertIn("places_details: 2 rows; places_nearby: 8 rows; places_aggregate: 90 rows", out)
        self.assertIn("sample places_nearby row:", out)
        self.assertNotIn(KEY, out + logs)

    def test_error_text_never_holds_the_key(self):
        body = io.BytesIO(f"API key {KEY} not valid".encode())
        exc = urllib.error.HTTPError("https://x.test", 400, "Bad Request", {}, body)
        self.addCleanup(exc.close)
        with mock.patch.object(places.httpjson.urllib.request, "urlopen", side_effect=exc), \
                mock.patch.object(places.httpjson.time, "sleep"):
            d, n, a, calls, errors = places.profile_site(KEY, {"site_id": "s", "place_id": "p"}, "r", FETCHED)
        self.assertEqual(len(errors), 1 + 45)
        self.assertIn("API key *** not valid", errors[0])
        self.assertNotIn(KEY, " ".join(errors))

    def test_all_calls_failing_exits_1(self):
        code, fake_bq, _, _ = self.run_main([], self.ENV, patched(
            details=(None, "x"), nearby=(None, "x"), aggregate=(None, "x")))
        self.assertEqual(code, 1)
        fake_bq.write_rows.assert_called_once()
        self.assertEqual(fake_bq.write_rows.call_args.args[4:], ([], [], []))

    def test_missing_key_exits(self):
        with mock.patch.dict(os.environ, {"MAPS_API_KEY": ""}):
            with self.assertRaises(SystemExit):
                main.get_key(False)

    def test_exit_code(self):
        self.assertEqual(main.exit_code(0, 0, 0), 1)
        self.assertEqual(main.exit_code(96, 96, 0), 1)
        self.assertEqual(main.exit_code(96, 5, 0), 0)
        self.assertEqual(main.exit_code(96, 1, 1), 1)  # a site without Details: let Cloud Run retry the run

    def test_iso_utc(self):
        self.assertEqual(main.iso(datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc)), FETCHED)


if __name__ == "__main__":
    unittest.main()
