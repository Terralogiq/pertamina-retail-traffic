#!/usr/bin/env python3
"""Load manual review labels into traffic.place_review_labels (one MERGE, re-runnable).

  labels.json  [{review_key, labels[], sentiment, praise_only, gist}, ...]
  site_id      looked up in traffic.v_place_reviews by review_key (an unknown key is an error)
  method       'manual', model_version 'taxonomy_v1', labeled_at = now

Rows go into a per-run staging table, are MERGEd on (review_key, method), and the staging table is dropped
(same pattern as reviews_job/bq.py). Needs google-cloud-bigquery and ADC: run it with .venv/bin/python.

Usage: .venv/bin/python scripts/load_review_labels.py <labels.json> [--project gcp-coe-sandbox]
         [--dataset traffic] [--location asia-southeast2] [--dry-run]
  --dry-run  validate and map the rows (reads v_place_reviews); no BigQuery writes
"""
import argparse
import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Taxonomy, row validation and the MERGE live in reviews_job/review_labels.py (the job image cannot import
# scripts/). Loaded by path under its own name, so reviews_job/ stays off sys.path.
_spec = importlib.util.spec_from_file_location(
    "review_labels", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reviews_job", "review_labels.py"))
review_labels = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review_labels)
TABLE, KEYS, SENTIMENTS, TAXONOMY, STAGE = (
    review_labels.TABLE, review_labels.KEYS, review_labels.SENTIMENTS, review_labels.TAXONOMY, review_labels.STAGE)
check_unique, check_label, merge_sql = review_labels.check_unique, review_labels.check_label, review_labels.merge_sql

METHOD = "manual"
MODEL_VERSION = "taxonomy_v1"

SITES_SQL = """
SELECT review_key, site_id
FROM `{project}.{dataset}.v_place_reviews`
WHERE review_key IN UNNEST(@keys)
"""


# --- pure helpers (no network, no BigQuery) -------------------------------------

def label_rows(items, site_by_key, labeled_at):
    """labels.json entries -> staging rows. Unknown review_key or duplicate key -> ValueError."""
    for item in items:
        check_label(item)
    unknown = sorted({i["review_key"] for i in items if i["review_key"] not in site_by_key})
    if unknown:
        raise ValueError(f"{len(unknown)} review_key(s) not in v_place_reviews: {unknown}")
    rows = [{
        "review_key": i["review_key"],
        "site_id": site_by_key[i["review_key"]],
        "labels": list(i["labels"]),
        "sentiment": i["sentiment"],
        "praise_only": i["praise_only"],
        "gist": i["gist"],
        "road_queue": None,   # the flag comes from Gemini prompt p4; manual rows stay NULL
        "method": METHOD,
        "model_version": MODEL_VERSION,
        "labeled_at": labeled_at,
    } for i in items]
    check_unique(rows, KEYS)
    return rows


# --- BigQuery ----------------------------------------------------------------------

def _schema(spec):
    from google.cloud import bigquery
    out = []
    for name, typ in spec:
        if typ.endswith("[]"):
            typ, mode = typ[:-2], "REPEATED"
        else:
            mode = "NULLABLE"
        out.append(bigquery.SchemaField(name, typ, mode=mode))
    return out


def read_sites(client, project, dataset, keys):
    """{review_key: site_id} for the keys found in v_place_reviews."""
    from google.cloud import bigquery
    job = client.query(
        SITES_SQL.format(project=project, dataset=dataset),
        job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ArrayQueryParameter("keys", "STRING", keys)]))
    return {r["review_key"]: r["site_id"] for r in job.result()}


def merge_rows(client, project, dataset, rows, now):
    from google.cloud import bigquery
    staging = f"{project}.{dataset}._stg_{TABLE}_{uuid.uuid4().hex[:12]}"
    schema = _schema(STAGE)
    tbl = bigquery.Table(staging, schema=schema)
    tbl.expires = now + timedelta(hours=3)  # cleans itself up if this process dies
    client.create_table(tbl)
    try:
        names = [s[0] for s in STAGE]
        client.load_table_from_json(
            [{c: (r[c].isoformat() if isinstance(r[c], datetime) else r[c]) for c in names} for r in rows], staging,
            job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_APPEND"),
        ).result()
        client.query(merge_sql(f"{project}.{dataset}.{TABLE}", staging)).result()
    finally:
        client.delete_table(staging, not_found_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("labels_json")
    ap.add_argument("--project", default="gcp-coe-sandbox")
    ap.add_argument("--dataset", default="traffic")
    ap.add_argument("--location", default="asia-southeast2")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.labels_json, encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list) or not items:
        sys.exit("labels.json must be a non-empty list")

    from google.cloud import bigquery
    client = bigquery.Client(project=args.project, location=args.location)
    now = datetime.now(timezone.utc)
    try:
        for item in items:
            check_label(item)
        site_by_key = read_sites(client, args.project, args.dataset, sorted({i["review_key"] for i in items}))
        rows = label_rows(items, site_by_key, now)
    except ValueError as e:
        sys.exit(f"not loading: {e}")
    if args.dry_run:
        print(f"{len(rows)} rows ready for {args.project}.{args.dataset}.{TABLE}; no writes (--dry-run)")
        return
    merge_rows(client, args.project, args.dataset, rows, now)
    print(f"merged {len(rows)} {METHOD} rows into {args.project}.{args.dataset}.{TABLE}")


if __name__ == "__main__":
    main()
