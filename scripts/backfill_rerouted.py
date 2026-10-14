#!/usr/bin/env python3
"""One-off backfill of traffic.traffic_snapshots.demo_rerouted for rows written before the collector computed it.

Reads rows with demo_rerouted IS NULL and a good call (duration_in_seconds IS NOT NULL; failed calls stay NULL),
computes the flag with collector/reroute.is_rerouted (the function the live ingest uses) from the stored
route_geometry and demo_distance_m against traffic.routes, and prints the counts. Rows whose route is not in
traffic.routes are not read and stay NULL.

--apply loads the flags into a per-run staging table and runs ONE MERGE keyed on (selected_route_id, slot_time)
that only touches rows where demo_rerouted IS NULL, so it is safe to re-run and never overwrites an ingested flag.
Needs google-cloud-bigquery and ADC: run it with .venv/bin/python.

Usage: .venv/bin/python scripts/backfill_rerouted.py [--apply] [--project gcp-coe-sandbox]
         [--dataset traffic] [--location asia-southeast2]
"""
import argparse
import os
import sys
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "collector"))

from bq import check_unique, line_points  # noqa: E402
from reroute import is_rerouted  # noqa: E402

TABLE = "traffic_snapshots"
KEYS = ("selected_route_id", "slot_time")
STAGE = [("selected_route_id", "STRING"), ("slot_time", "TIMESTAMP"), ("demo_rerouted", "BOOL")]

READ_SQL = """
SELECT t.selected_route_id, t.slot_time, t.demo_distance_m,
       ST_ASGEOJSON(t.route_geometry) AS actual_geojson,
       r.expected_distance_m, ST_ASGEOJSON(r.expected_polyline) AS expected_geojson
FROM `{project}.{dataset}.traffic_snapshots` t
JOIN `{project}.{dataset}.routes` r USING (selected_route_id)
WHERE t.demo_rerouted IS NULL AND t.duration_in_seconds IS NOT NULL
"""


# --- pure helpers (no network, no BigQuery) -------------------------------------

def flag_rows(rows):
    """Read rows -> staging rows {selected_route_id, slot_time, demo_rerouted}, with the live ingest's rule."""
    return [{
        "selected_route_id": r["selected_route_id"],
        "slot_time": r["slot_time"],
        "demo_rerouted": is_rerouted(
            r["expected_distance_m"],
            int(r["demo_distance_m"]) if r["demo_distance_m"] is not None else None,
            line_points(r["actual_geojson"]),
            line_points(r["expected_geojson"]),
        ),
    } for r in rows]


def summarize(flagged):
    """(rows, true count, false count, Counter of true flags per route)."""
    per_route = Counter(r["selected_route_id"] for r in flagged if r["demo_rerouted"])
    n_true = sum(per_route.values())
    return len(flagged), n_true, len(flagged) - n_true, per_route


def report(flagged):
    n, n_true, n_false, per_route = summarize(flagged)
    lines = [f"rows read: {n}", f"would set true: {n_true}", f"would set false: {n_false}", "true per route:"]
    lines += [f"  {route}: {c}" for route, c in sorted(per_route.items())] or ["  (none)"]
    return "\n".join(lines)


def slot_bounds(flagged):
    """(min, max) slot_time of the rows: lets the MERGE prune to the partitions it needs."""
    slots = [r["slot_time"] for r in flagged]
    return min(slots), max(slots)


def merge_sql(target, staging):
    """MERGE the staging flags into `target`, only where demo_rerouted is still NULL.

    The slot_time range term lets BigQuery prune the partitions of traffic_snapshots.
    """
    return (
        f"MERGE `{target}` T\nUSING `{staging}` S\n"
        "ON T.selected_route_id = S.selected_route_id AND T.slot_time = S.slot_time"
        " AND T.slot_time BETWEEN @min_slot AND @max_slot\n"
        "WHEN MATCHED AND T.demo_rerouted IS NULL THEN UPDATE SET demo_rerouted = S.demo_rerouted"
    )


# --- BigQuery ----------------------------------------------------------------------

def read_rows(client, project, dataset):
    sql = READ_SQL.format(project=project, dataset=dataset)
    return [dict(r.items()) for r in client.query(sql).result()]


def apply_flags(client, project, dataset, flagged, now):
    """Stage the flags and MERGE them in. Returns the number of rows the MERGE updated."""
    from google.cloud import bigquery
    check_unique(flagged, KEYS)
    staging = f"{project}.{dataset}._stg_backfill_rerouted_{uuid.uuid4().hex[:12]}"
    schema = [bigquery.SchemaField(c, t) for c, t in STAGE]
    tbl = bigquery.Table(staging, schema=schema)
    tbl.expires = now + timedelta(hours=3)  # cleans itself up if this process dies
    client.create_table(tbl)
    try:
        client.load_table_from_json(
            [{c: (r[c].isoformat() if isinstance(r[c], datetime) else r[c]) for c, _ in STAGE} for r in flagged],
            staging,
            job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_APPEND"),
        ).result()
        lo, hi = slot_bounds(flagged)
        job = client.query(merge_sql(f"{project}.{dataset}.{TABLE}", staging),
                           job_config=bigquery.QueryJobConfig(query_parameters=[
                               bigquery.ScalarQueryParameter("min_slot", "TIMESTAMP", lo),
                               bigquery.ScalarQueryParameter("max_slot", "TIMESTAMP", hi)]))
        job.result()
        return job.num_dml_affected_rows
    finally:
        client.delete_table(staging, not_found_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the flags; default is a read-only dry run")
    ap.add_argument("--project", default="gcp-coe-sandbox")
    ap.add_argument("--dataset", default="traffic")
    ap.add_argument("--location", default="asia-southeast2")
    args = ap.parse_args()

    from google.cloud import bigquery
    client = bigquery.Client(project=args.project, location=args.location)
    flagged = flag_rows(read_rows(client, args.project, args.dataset))
    print(report(flagged))
    if not flagged:
        return
    if not args.apply:
        print("dry run: no writes (pass --apply to write)")
        return
    updated = apply_flags(client, args.project, args.dataset, flagged, datetime.now(timezone.utc))
    print(f"updated {updated} rows in {args.project}.{args.dataset}.{TABLE}")


if __name__ == "__main__":
    main()
