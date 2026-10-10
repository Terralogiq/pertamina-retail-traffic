#!/usr/bin/env python3
"""Export a human-validation sample of labelled reviews (CSV for Excel + README).

All neg/mixed reviews plus pos reviews to fill the sample to --size, with pos
allocated across sites in proportion to each site's pos count (largest remainder).

Usage: python3 scripts/export_validation_sample.py <labels.json> <reviews.json> <out_dir> [--seed 20261010]
"""
import argparse
import csv
import json
import os
import random
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "plans", "complaints-analysis.md")
COLUMNS = ["review_key", "site_id", "rating", "text", "labels", "sentiment",
           "corrected_labels", "corrected_sentiment", "notes"]
SIZE = 100


def allocate(counts, total):
    """Largest-remainder allocation of `total` across keys, proportional to counts, capped at counts."""
    pool = sum(counts.values())
    total = min(total, pool)
    if pool == 0:
        return {k: 0 for k in counts}
    quota = {k: total * v / pool for k, v in counts.items()}
    alloc = {k: int(q) for k, q in quota.items()}
    order = sorted(counts, key=lambda k: (-(quota[k] - alloc[k]), str(k)))
    for k in order[: total - sum(alloc.values())]:
        alloc[k] += 1
    return alloc


def select(labels, reviews, seed, size=SIZE):
    by_key = {r["review_key"]: r for r in reviews}
    missing = sorted({lab["review_key"] for lab in labels if lab["review_key"] not in by_key})
    if missing:
        raise ValueError(f"{len(missing)} labelled review_key(s) not in reviews.json: {missing}")
    rows = []
    for lab in labels:
        rev = by_key[lab["review_key"]]
        rows.append({"review_key": lab["review_key"], "site_id": rev["site_id"],
                     "rating": rev.get("rating"), "text": rev.get("text"),
                     "labels": ";".join(lab["labels"]), "sentiment": lab["sentiment"],
                     "corrected_labels": "", "corrected_sentiment": "", "notes": ""})
    rng = random.Random(seed)
    chosen = [r for r in rows if r["sentiment"] in ("neg", "mixed")]
    pos_by_site = {}
    for r in sorted((r for r in rows if r["sentiment"] == "pos"), key=lambda r: r["review_key"]):
        pos_by_site.setdefault(r["site_id"], []).append(r)
    alloc = allocate({s: len(v) for s, v in pos_by_site.items()}, size - len(chosen))
    for s in sorted(pos_by_site):
        chosen += rng.sample(pos_by_site[s], alloc[s])
    chosen.sort(key=lambda r: r["review_key"])
    rng.shuffle(chosen)
    return chosen


def readme_sections():
    with open(PLAN, encoding="utf-8") as f:
        text = f.read()
    # Only what the reviewer judges against: sentiment rules, labelling decisions, category table.
    rules = re.search(r"^- `sentiment`.*?(?=^- Masking)", text, re.S | re.M).group(0).strip()
    table = re.search(r"^### Category definitions\n.*?(?=^## )", text, re.S | re.M).group(0).strip()
    return f"## Rules\n\n{rules}\n\n{table}"


def readme(n):
    return f"""# Validation sample for review labels

{n} Google reviews of the 10 SPBU, labelled by an automated reader. Please check the labels.
File: `validation_sample.csv` (UTF-8 with BOM; open in Excel or Google Sheets).

## What to do

- Read `text`, compare with `labels` (semicolon-separated categories) and `sentiment`.
- If you agree with both, leave `corrected_labels`, `corrected_sentiment` and `notes` blank. Blank means agree.
- If you disagree, fill only the column that is wrong:
  - `corrected_labels`: the full corrected list, semicolon-separated, using the category names below. To mean "no category", write `none`. Blank means you agree.
  - `corrected_sentiment`: one of `pos`, `mixed`, `neg`.
  - `notes`: optional reason.
- Do not edit the other columns.

{readme_sections()}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels")
    ap.add_argument("reviews")
    ap.add_argument("out_dir")
    ap.add_argument("--seed", type=int, default=20261010)
    args = ap.parse_args()
    with open(args.labels, encoding="utf-8") as f:
        labels = json.load(f)
    with open(args.reviews, encoding="utf-8") as f:
        reviews = json.load(f)
    rows = select(labels, reviews, args.seed)
    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "validation_sample.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(args.out_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme(len(rows)))
    n_nm = sum(r["sentiment"] in ("neg", "mixed") for r in rows)
    print(f"wrote {len(rows)} rows ({n_nm} neg/mixed) to {args.out_dir}")


if __name__ == "__main__":
    main()
