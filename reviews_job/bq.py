"""BigQuery access: the only module that imports google.cloud (lazily, inside functions).

Same pattern as places_job/bq.py (vendored in shape, not imported: the build context is reviews_job/).
Each table is written with ONE MERGE per run, from a per-run staging table (raw as JSON text).
- place_reviews: MERGE on review_key. New reviews are inserted; a review seen again gets last_seen_at and the
  union of seen_in. Re-running the same poll, or a Cloud Run retry, therefore changes nothing but last_seen_at.
- place_review_snapshots: MERGE on (run_id, site_id, variant), like the places tables, so a retry of the same
  Cloud Run execution overwrites its own rows instead of duplicating them.
"""
import uuid
from datetime import timedelta, timezone

SITES_SQL = """
SELECT site_id, place_id
FROM `{project}.{dataset}.sites`
WHERE place_id IS NOT NULL
ORDER BY site_id
"""

# (column, type). "X[]" = REPEATED. Staging columns and target columns share names and order.
REVIEWS_STAGE = [
    ("review_key", "STRING"), ("site_id", "STRING"), ("place_id", "STRING"),
    ("published_at", "TIMESTAMP"), ("rating", "INT64"), ("text", "STRING"),
    ("language", "STRING"), ("original_language", "STRING"),
    ("first_seen_at", "TIMESTAMP"), ("last_seen_at", "TIMESTAMP"), ("seen_in", "STRING[]"),
    ("raw", "STRING"),  # JSON text; JSON in the target
]
REVIEWS_KEYS = ("review_key",)

SNAPSHOTS_STAGE = [
    ("run_id", "STRING"), ("site_id", "STRING"), ("mode", "STRING"), ("variant", "STRING"),
    ("fetched_at", "TIMESTAMP"), ("user_ratings_total", "INT64"), ("rating", "FLOAT64"),
    ("n_reviews", "INT64"),
    ("raw", "STRING"),  # JSON text; JSON in the target
]
SNAPSHOTS_KEYS = ("run_id", "site_id", "variant")

PARSE_RAW = "PARSE_JSON(S.raw, wide_number_mode => 'round')"

# The snapshots table is partitioned by DATE(fetched_at): a retry starts at most minutes after the first
# attempt, so a one-day window on the target prunes the MERGE to the partitions that can hold the run.
WINDOW = "T.fetched_at >= TIMESTAMP_SUB(@fetched_at, INTERVAL 1 DAY)"


def reviews_merge_sql(target, source):
    """MERGE `source` (staging) into place_reviews. A match only refreshes last_seen_at and seen_in.

    rating, text and raw are NOT refreshed: published_at is the original time and the row keeps what was
    first seen (an edit of a review is not tracked). The target is not partitioned, so the ON clause cannot prune.
    """
    cols = [s[0] for s in REVIEWS_STAGE]
    vals = [PARSE_RAW if c == "raw" else f"S.{c}" for c in cols]
    return (
        # BigQuery rejects a correlated subquery in UPDATE SET, so the seen_in union is computed in the source.
        f"MERGE `{target}` T\nUSING (\n  SELECT S.*, ARRAY(SELECT DISTINCT v FROM UNNEST(ARRAY_CONCAT(IFNULL(P.seen_in, []), "
        f"S.seen_in)) AS v ORDER BY v) AS merged_seen_in\n  FROM `{source}` S LEFT JOIN `{target}` P USING (review_key)\n) S\n"
        "ON T.review_key = S.review_key\n"
        "WHEN MATCHED THEN UPDATE SET last_seen_at = GREATEST(T.last_seen_at, S.last_seen_at), "
        "seen_in = S.merged_seen_in\n"
        f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join(vals)})"
    )


def snapshots_merge_sql(target, source):
    """MERGE `source` into place_review_snapshots on (run_id, site_id, variant); matched rows are overwritten."""
    cols = [s[0] for s in SNAPSHOTS_STAGE]
    non_key = [c for c in cols if c not in SNAPSHOTS_KEYS]
    sel = lambda c: PARSE_RAW if c == "raw" else f"S.{c}"  # noqa: E731
    on = " AND ".join([f"T.{k} = S.{k}" for k in SNAPSHOTS_KEYS] + [WINDOW])
    return (
        f"MERGE `{target}` T\nUSING `{source}` S\nON {on}\n"
        f"WHEN MATCHED THEN UPDATE SET {', '.join(f'{c} = {sel(c)}' for c in non_key)}\n"
        f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join(sel(c) for c in cols)})"
    )


def check_unique(rows, keys):
    seen = set()
    for r in rows:
        k = tuple(r[c] for c in keys)
        if k in seen:
            raise ValueError(f"duplicate key {k}: a MERGE source must have one row per key")
        seen.add(k)


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


def _client(project, location):
    from google.cloud import bigquery
    return bigquery.Client(project=project, location=location)


def read_sites(project, dataset, location):
    """Sites with a place_id, as dicts {site_id, place_id}."""
    client = _client(project, location)
    rows = client.query(SITES_SQL.format(project=project, dataset=dataset)).result()
    return [dict(r.items()) for r in rows]


def _merge_table(client, project, dataset, table, stage, keys, rows, fetched_at, merge_sql):
    from google.cloud import bigquery
    check_unique(rows, keys)
    staging = f"{project}.{dataset}._stg_{table}_{uuid.uuid4().hex[:12]}"
    schema = _schema(stage)
    tbl = bigquery.Table(staging, schema=schema)
    tbl.expires = fetched_at.astimezone(timezone.utc) + timedelta(hours=3)  # cleans itself up if this process dies
    client.create_table(tbl)
    try:
        names = [s[0] for s in stage]
        client.load_table_from_json(
            [{c: r[c] for c in names} for r in rows], staging,
            job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_APPEND"),
        ).result()
        sql = merge_sql(f"{project}.{dataset}.{table}", staging)
        params = [bigquery.ScalarQueryParameter("fetched_at", "TIMESTAMP", fetched_at)] if "@fetched_at" in sql else []
        client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    finally:
        client.delete_table(staging, not_found_ok=True)


def write_rows(project, dataset, location, fetched_at, reviews, snapshots):
    """One MERGE per table. Empty row lists are skipped."""
    client = _client(project, location)
    for table, stage, keys, rows, sql in (
        ("place_reviews", REVIEWS_STAGE, REVIEWS_KEYS, reviews, reviews_merge_sql),
        ("place_review_snapshots", SNAPSHOTS_STAGE, SNAPSHOTS_KEYS, snapshots, snapshots_merge_sql),
    ):
        if rows:
            _merge_table(client, project, dataset, table, stage, keys, rows, fetched_at, sql)
