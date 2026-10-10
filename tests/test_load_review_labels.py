"""Unit tests for the pure helpers in scripts/load_review_labels.py. No network, no BigQuery."""
import importlib.util
import os
import re
import unittest
from datetime import datetime, timezone

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
_spec = importlib.util.spec_from_file_location("load_review_labels", os.path.join(SCRIPTS, "load_review_labels.py"))
lrl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lrl)

NOW = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)


def item(key="k1", **kw):
    d = {"review_key": key, "labels": ["antrian", "pelayanan_petugas"], "sentiment": "neg",
         "praise_only": False, "gist": "Long queue, rude attendant."}
    d.update(kw)
    return d


class RowMappingTest(unittest.TestCase):
    def test_row_fields(self):
        rows = lrl.label_rows([item("k1"), item("k2", labels=[], sentiment="pos", praise_only=True)],
                              {"k1": "34.121.03", "k2": "34.000.01"}, NOW)
        self.assertEqual(rows[0], {
            "review_key": "k1", "site_id": "34.121.03", "labels": ["antrian", "pelayanan_petugas"],
            "sentiment": "neg", "praise_only": False, "gist": "Long queue, rude attendant.",
            "method": "manual", "model_version": "taxonomy_v1", "labeled_at": NOW})
        self.assertEqual(rows[1]["site_id"], "34.000.01")
        self.assertEqual(rows[1]["labels"], [])

    def test_rows_match_staging_columns(self):
        row = lrl.label_rows([item()], {"k1": "s"}, NOW)[0]
        self.assertEqual(list(row), [c for c, _ in lrl.STAGE])

    def test_unknown_review_key_fails_loudly(self):
        with self.assertRaises(ValueError) as cm:
            lrl.label_rows([item("k1"), item("nope")], {"k1": "s"}, NOW)
        self.assertIn("nope", str(cm.exception))
        self.assertIn("not in v_place_reviews", str(cm.exception))

    def test_duplicate_review_key_fails(self):
        with self.assertRaises(ValueError):
            lrl.label_rows([item("k1"), item("k1")], {"k1": "s"}, NOW)

    def test_bad_entries(self):
        for bad in (item(labels=["nonsense"]), item(sentiment="neutral"), item(praise_only="no"),
                    item(labels="antrian"), item(praise_only=True), item(sentiment="pos", praise_only=False), item(gist=None), item(key="")):
            with self.assertRaises(ValueError, msg=bad):
                lrl.label_rows([bad], {"k1": "s", "": "s"}, NOW)


class DdlTest(unittest.TestCase):
    def setUp(self):
        root = os.path.dirname(SCRIPTS)
        with open(os.path.join(root, "sql", "ddl.sql")) as f:
            self.sql = f.read()
        m = re.search(r"CREATE TABLE IF NOT EXISTS traffic\.place_review_labels \((.*?)\n\)\n(.*?;)", self.sql, re.S)
        self.cols = [c.group(1) for c in re.finditer(r"^  (\w+)\s+\S", m.group(1), re.M)]
        self.tail = m.group(2)

    def test_stage_matches_ddl(self):
        self.assertEqual([c for c, _ in lrl.STAGE], self.cols)

    def test_table_shape_and_no_text_columns(self):
        self.assertEqual(self.tail, "CLUSTER BY site_id;")
        self.assertNotIn("PARTITION BY", self.tail)
        for c in self.cols:
            self.assertNotIn(c, ("text", "raw"))
            self.assertNotIn("author", c)


class CheckUniqueTest(unittest.TestCase):
    def test_duplicate_on_composite_key(self):
        rows = [{"review_key": "a", "method": "manual"}, {"review_key": "a", "method": "manual"}]
        with self.assertRaises(ValueError):
            lrl.check_unique(rows, lrl.KEYS)

    def test_same_review_other_method_is_fine(self):
        lrl.check_unique([{"review_key": "a", "method": "manual"}, {"review_key": "a", "method": "gemini"}], lrl.KEYS)


class MergeSqlTest(unittest.TestCase):
    def setUp(self):
        self.sql = lrl.merge_sql("p.traffic.place_review_labels", "p.traffic._stg_x")

    def test_merge_key_and_tables(self):
        self.assertIn("MERGE `p.traffic.place_review_labels` T", self.sql)
        self.assertIn("USING `p.traffic._stg_x` S", self.sql)
        self.assertIn("ON T.review_key = S.review_key AND T.method = S.method", self.sql)

    def test_matched_overwrites_non_key_columns_only(self):
        update = self.sql.split("WHEN MATCHED THEN UPDATE SET ")[1].split("\nWHEN NOT MATCHED")[0]
        assigned = [a.split(" = ")[0] for a in update.split(", ")]
        self.assertEqual(assigned, ["site_id", "labels", "sentiment", "praise_only", "gist", "model_version", "labeled_at"])

    def test_insert_lists_every_column(self):
        insert = self.sql.split("WHEN NOT MATCHED THEN INSERT ")[1]
        cols = ", ".join(c for c, _ in lrl.STAGE)
        vals = ", ".join(f"S.{c}" for c, _ in lrl.STAGE)
        self.assertEqual(insert, f"({cols}) VALUES ({vals})")


if __name__ == "__main__":
    unittest.main()
