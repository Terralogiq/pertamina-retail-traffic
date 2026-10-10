"""Unit tests for scripts/export_validation_sample.py. Synthetic data, no network."""
import importlib.util
import os
import unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
_spec = importlib.util.spec_from_file_location("export_validation_sample", os.path.join(SCRIPTS, "export_validation_sample.py"))
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def synth():
    labels, reviews = [], []
    for i in range(130):
        sent = "neg" if i < 20 else "mixed" if i < 40 else "pos"
        site = f"s{i % 4}"
        labels.append({"review_key": f"k{i}", "labels": ["antrian", "harga"] if sent != "pos" else [],
                       "sentiment": sent, "praise_only": sent == "pos", "gist": "g"})
        reviews.append({"review_key": f"k{i}", "site_id": site, "rating": 3, "text": f"t{i}", "author": "x"})
    return labels, reviews


class AllocateTest(unittest.TestCase):
    def test_sums_to_total_and_proportional(self):
        a = ev.allocate({"a": 50, "b": 30, "c": 20}, 7)
        self.assertEqual(sum(a.values()), 7)
        self.assertEqual(a, {"a": 4, "b": 2, "c": 1})

    def test_capped_at_pool(self):
        self.assertEqual(sum(ev.allocate({"a": 2, "b": 1}, 10).values()), 3)


class SelectTest(unittest.TestCase):
    def test_size_and_all_neg_mixed(self):
        labels, reviews = synth()
        rows = ev.select(labels, reviews, 1)
        self.assertEqual(len(rows), 100)
        keys = {r["review_key"] for r in rows}
        self.assertTrue(all(f"k{i}" in keys for i in range(40)))
        self.assertEqual(sum(r["sentiment"] == "pos" for r in rows), 60)

    def test_deterministic_and_seed_sensitive(self):
        labels, reviews = synth()
        a = [r["review_key"] for r in ev.select(labels, reviews, 1)]
        self.assertEqual(a, [r["review_key"] for r in ev.select(labels, reviews, 1)])
        self.assertNotEqual(a, [r["review_key"] for r in ev.select(labels, reviews, 2)])

    def test_missing_review_key_fails(self):
        labels, reviews = synth()
        with self.assertRaises(ValueError) as cm:
            ev.select(labels, reviews[1:], 1)
        self.assertIn("1 labelled review_key(s)", str(cm.exception))
        self.assertIn("k0", str(cm.exception))

    def test_columns_and_no_author(self):
        labels, reviews = synth()
        rows = ev.select(labels, reviews, 1)
        self.assertTrue(all(list(r) == ev.COLUMNS for r in rows))
        self.assertEqual(rows[0]["corrected_labels"], "")
        self.assertIn("antrian;harga", {r["labels"] for r in rows})


if __name__ == "__main__":
    unittest.main()
