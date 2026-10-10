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
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone

TABLE = "place_review_labels"
METHOD = "manual"
MODEL_VERSION = "taxonomy_v1"
KEYS = ("review_key", "method")
SENTIMENTS = ("neg", "mixed", "pos")
TAXONOMY = (
    "antrian", "pelayanan_petugas", "bbm_kosong", "kualitas_bbm", "takaran", "pembayaran",
    "harga", "kebersihan", "toilet", "fasilitas", "keamanan_lalu_lintas", "lainnya",
)

# (column, type). "X[]" = REPEATED. Staging columns and target columns share names and order.
STAGE = [
    ("review_key", "STRING"), ("site_id", "STRING"), ("labels", "STRING[]"), ("sentiment", "STRING"),
    ("praise_only", "BOOL"), ("gist", "STRING"), ("method", "STRING"), ("model_version", "STRING"),
    ("labeled_at", "TIMESTAMP"),
]

SITES_SQL = """
SELECT review_key, site_id
FROM `{project}.{dataset}.v_place_reviews`
WHERE review_key IN UNNEST(@keys)
"""


# --- pure helpers (no network, no BigQuery) -------------------------------------

def check_unique(rows, keys):
    seen = set()
    for r in rows:
        k = tuple(r[c] for c in keys)
        if k in seen:
            raise ValueError(f"duplicate key {k}: a MERGE source must have one row per key")
        seen.add(k)


def check_label(item):
    """Raise ValueError when a labels.json entry is not usable; the message never includes the gist."""
    key = item.get("review_key")
    if not isinstance(key, str) or not key:
        raise ValueError("entry without review_key")
    labels = item.get("labels")
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValueError(f"{key}: labels must be a list of strings")
    bad = [x for x in labels if x not in TAXONOMY]
    if bad:
        raise ValueError(f"{key}: labels outside the taxonomy: {bad}")
    if item.get("sentiment") not in SENTIMENTS:
        raise ValueError(f"{key}: sentiment must be one of {SENTIMENTS}")
    if not isinstance(item.get("praise_only"), bool):
        raise ValueError(f"{key}: praise_only must be a boolean")
    if item["praise_only"] != (item["sentiment"] == "pos"):
        raise ValueError(f"{key}: praise_only must be true exactly when sentiment is pos")
    if not isinstance(item.get("gist"), str):
        raise ValueError(f"{key}: gist must be a string")


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
        "method": METHOD,
        "model_version": MODEL_VERSION,
        "labeled_at": labeled_at,
    } for i in items]
    check_unique(rows, KEYS)
    return rows


def merge_sql(target, source):
    """MERGE `source` (staging) into place_review_labels on (review_key, method); matched rows are overwritten."""
    cols = [s[0] for s in STAGE]
    non_key = [c for c in cols if c not in KEYS]
    on = " AND ".join(f"T.{k} = S.{k}" for k in KEYS)
    return (
        f"MERGE `{target}` T\nUSING `{source}` S\nON {on}\n"
        f"WHEN MATCHED THEN UPDATE SET {', '.join(f'{c} = S.{c}' for c in non_key)}\n"
        f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join(f'S.{c}' for c in cols)})"
    )


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
