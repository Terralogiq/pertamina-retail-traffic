"""BigQuery access: the only module that imports google.cloud (lazily, inside functions).

Same pattern as collector/bq.py (vendored in shape, not imported: the build context is places_job/).
Writes each table with ONE MERGE per run: the rows are loaded into a per-run staging table
(raw as JSON text), then merged on a key that starts with run_id. A retry of the same run
(Cloud Run task retry, same CLOUD_RUN_EXECUTION) overwrites its own rows instead of duplicating
them; a new run has a new run_id and only adds rows.
"""
import uuid
from datetime import timedelta, timezone

SITES_SQL = """
SELECT site_id, place_id
FROM `{project}.{dataset}.sites`
WHERE place_id IS NOT NULL
ORDER BY site_id
"""

# (column, type[, sub-fields]). "X[]" = REPEATED; "RECORD[]" takes the sub-field list.
# Staging columns and target columns share names (the target ARRAY<STRUCT<..>> matches field for field).
REVIEW_FIELDS = [
    ("rating", "INT64"), ("text", "STRING"), ("language", "STRING"),
    ("publish_time", "TIMESTAMP"), ("author_name", "STRING"),
]
DETAILS_STAGE = [
    ("run_id", "STRING"), ("site_id", "STRING"), ("fetched_at", "TIMESTAMP"),
    ("place_id", "STRING"), ("display_name", "STRING"), ("rating", "FLOAT64"),
    ("user_rating_count", "INT64"), ("business_status", "STRING"), ("primary_type", "STRING"),
    ("open_now", "BOOL"), ("weekday_descriptions", "STRING[]"), ("utc_offset_minutes", "INT64"),
    ("reviews", "RECORD[]", REVIEW_FIELDS),
    ("raw", "STRING"),  # JSON text; JSON in the target
]
DETAILS_KEYS = ("run_id", "site_id")

NEARBY_STAGE = [
    ("run_id", "STRING"), ("site_id", "STRING"), ("radius_m", "INT64"), ("place_id", "STRING"),
    ("fetched_at", "TIMESTAMP"), ("name", "STRING"), ("brand", "STRING"), ("primary_type", "STRING"),
    ("distance_m", "INT64"), ("rating", "FLOAT64"), ("user_rating_count", "INT64"),
    ("business_status", "STRING"), ("rank", "INT64"), ("raw", "STRING"),
]
NEARBY_KEYS = ("run_id", "site_id", "radius_m", "place_id")

AGGREGATE_STAGE = [
    ("run_id", "STRING"), ("site_id", "STRING"), ("place_type", "STRING"), ("radius_m", "INT64"),
    ("fetched_at", "TIMESTAMP"), ("count", "INT64"), ("raw", "STRING"),
]
AGGREGATE_KEYS = ("run_id", "site_id", "place_type", "radius_m")

# Staging column -> SQL over the staging alias S.
EXPR = {"raw": "PARSE_JSON(S.raw, wide_number_mode => 'round')"}

# Tables are partitioned by DATE(fetched_at). A retry starts at most minutes after the first
# attempt, so a one-day window on the target prunes the MERGE to the partitions that can hold the run.
WINDOW = "T.fetched_at >= TIMESTAMP_SUB(@fetched_at, INTERVAL 1 DAY)"


def merge_sql(target, source, stage, keys):
    """MERGE `source` (staging table) into `target`, keyed on `keys` (run_id first).

    Matched rows are overwritten (a retry replaces its own rows, including fetched_at).
    """
    cols = [s[0] for s in stage]
    non_key = [c for c in cols if c not in keys]
    sel = lambda c: EXPR.get(c, f"S.{c}")  # noqa: E731
    on = " AND ".join([f"T.{k} = S.{k}" for k in keys] + [WINDOW])
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
    for name, typ, *sub in spec:
        if typ.endswith("[]"):
            typ, mode = typ[:-2], "REPEATED"
        else:
            mode = "NULLABLE"
        out.append(bigquery.SchemaField(name, typ, mode=mode, fields=_schema(sub[0]) if sub else ()))
    return out


def _client(project, location):
    from google.cloud import bigquery
    return bigquery.Client(project=project, location=location)


def read_sites(project, dataset, location):
    """Sites with a place_id, as dicts {site_id, place_id}."""
    client = _client(project, location)
    rows = client.query(SITES_SQL.format(project=project, dataset=dataset)).result()
    return [dict(r.items()) for r in rows]


def _merge_table(client, project, dataset, table, stage, keys, rows, fetched_at):
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
        sql = merge_sql(f"{project}.{dataset}.{table}", staging, stage, keys)
        client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("fetched_at", "TIMESTAMP", fetched_at)])).result()
    finally:
        client.delete_table(staging, not_found_ok=True)


def write_rows(project, dataset, location, fetched_at, details, nearby, aggregate):
    """One MERGE per table. Empty row lists are skipped."""
    client = _client(project, location)
    for table, stage, keys, rows in (
        ("places_details", DETAILS_STAGE, DETAILS_KEYS, details),
        ("places_nearby", NEARBY_STAGE, NEARBY_KEYS, nearby),
        ("places_aggregate", AGGREGATE_STAGE, AGGREGATE_KEYS, aggregate),
    ):
        if rows:
            _merge_table(client, project, dataset, table, stage, keys, rows, fetched_at)
