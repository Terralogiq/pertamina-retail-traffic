"""Thin BigQuery wrapper. Parameterised queries only; google-cloud-bigquery is imported lazily so tests can run
without it (tests patch `bq.query`).

Every query on traffic_snapshots / v_traffic / weather_slots must filter slot_time (the partition column), at
most MAX_DAYS wide; see docs/plans/dashboard.md.
"""
from datetime import datetime

PROJECT = "gcp-coe-sandbox"
DATASET = "traffic"
LOCATION = "asia-southeast2"
MAX_DAYS = 31

_client = None


def table(name):
    """Fully qualified, backquoted table or view name."""
    return f"`{PROJECT}.{DATASET}.{name}`"


def _get_client():
    global _client
    if _client is None:
        from google.cloud import bigquery

        _client = bigquery.Client(project=PROJECT, location=LOCATION)
    return _client


def _param(name, value):
    from google.cloud import bigquery

    if isinstance(value, bool):  # before int: bool is an int subclass
        kind = "BOOL"
    elif isinstance(value, int):
        kind = "INT64"
    elif isinstance(value, float):
        kind = "FLOAT64"
    elif isinstance(value, datetime):
        kind = "TIMESTAMP"
    else:
        kind = "STRING"
    return bigquery.ScalarQueryParameter(name, kind, value)


def query(sql, params=None):
    """Run `sql` with @named parameters; return the rows as a list of dicts."""
    from google.cloud import bigquery

    config = bigquery.QueryJobConfig(
        query_parameters=[_param(k, v) for k, v in (params or {}).items()])
    rows = _get_client().query(sql, job_config=config).result()
    return [dict(row.items()) for row in rows]
