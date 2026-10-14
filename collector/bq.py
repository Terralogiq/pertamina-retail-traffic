"""BigQuery access: the only module that imports google.cloud (lazily, inside functions).

Reads the active routes; writes each table with ONE MERGE per run. The rows are first loaded
into a per-run staging table (geometry as WKT text, raw as JSON text), then merged, so a
retried run overwrites its own rows instead of duplicating them.
"""
import uuid
from datetime import timedelta

from slots import utc_now

# (column, BigQuery type) of the staging tables. Staging columns and target columns share names.
TRAFFIC_STAGE = [
    ("selected_route_id", "STRING"), ("display_name", "STRING"), ("record_time", "TIMESTAMP"),
    ("duration_in_seconds", "FLOAT64"), ("static_duration_in_seconds", "FLOAT64"),
    ("route_geometry", "STRING"),  # WKT; GEOGRAPHY in the target
    ("slot_time", "TIMESTAMP"), ("static_ratio", "FLOAT64"), ("speed_kmh", "FLOAT64"),
    ("demo_distance_m", "INT64"), ("demo_rerouted", "BOOL"), ("demo_routing_preference", "STRING"),
    ("raw", "STRING"),  # JSON text; JSON in the target
    ("fetched_at", "TIMESTAMP"),
]
TRAFFIC_KEYS = ("selected_route_id", "slot_time")
TRAFFIC_GUARD = "duration_in_seconds"  # null = the call failed
# Target-only columns written on INSERT: arrays the demo always leaves empty.
TRAFFIC_INSERT_ONLY = {
    "road_segment_ids": "ARRAY<STRING>[]",
    "speed_reading_intervals": "ARRAY<STRUCT<interval_coordinates GEOGRAPHY, speed STRING>>[]",
}

WEATHER_STAGE = [
    ("site_id", "STRING"), ("slot_time", "TIMESTAMP"), ("forecast_init_time", "TIMESTAMP"),
    ("temperature_c", "FLOAT64"), ("dewpoint_c", "FLOAT64"), ("relative_humidity", "FLOAT64"),
    ("precipitation_mm", "FLOAT64"), ("rain_flag", "BOOL"), ("wind_speed_kmh", "FLOAT64"),
    ("wind_direction_deg", "FLOAT64"), ("msl_pressure_hpa", "FLOAT64"), ("source", "STRING"),
    ("ensemble_stat", "STRING"), ("demo_condition_type", "STRING"), ("demo_condition_text", "STRING"),
    ("demo_rain_flag", "BOOL"),
    ("demo_icon_uri", "STRING"), ("demo_precip_probability", "FLOAT64"),
    ("demo_thunderstorm_prob", "FLOAT64"), ("demo_feels_like_c", "FLOAT64"), ("demo_uv_index", "INT64"),
    ("demo_visibility_km", "FLOAT64"), ("demo_cloud_cover", "INT64"), ("demo_is_daytime", "BOOL"),
    ("raw", "STRING"), ("fetched_at", "TIMESTAMP"),
]
WEATHER_KEYS = ("site_id", "slot_time")
WEATHER_GUARD = "temperature_c"  # null = the call failed

# Staging column -> SQL over the staging alias S.
EXPR = {
    "route_geometry": "SAFE.ST_GEOGFROMTEXT(S.route_geometry)",  # one bad polyline must not fail the slot
    "raw": "PARSE_JSON(S.raw, wide_number_mode => 'round')",
}

ROUTES_SQL = """
SELECT selected_route_id, display_name, site_id, side, call_id, leg_index,
       ST_Y(origin) AS origin_lat, ST_X(origin) AS origin_lng,
       ST_Y(destination) AS dest_lat, ST_X(destination) AS dest_lng,
       demo_origin_heading AS origin_heading, demo_dest_heading AS dest_heading,
       expected_distance_m,
       ST_ASGEOJSON(expected_polyline) AS expected_polyline
FROM `{project}.{dataset}.routes`
WHERE active
ORDER BY call_id, leg_index
"""


def merge_sql(target, source, stage, keys, insert_only=None, guard=None):
    """MERGE `source` (staging table) into `target`, keyed on `keys`, for the slot in @slot_time.

    Matched rows are overwritten (a retry replaces an earlier failed row), except that with `guard`
    (a column that is null only for a failed call) a failed source row never overwrites a good
    target row. The `T.slot_time = @slot_time` term lets BigQuery prune to the slot's partition.
    """
    cols = [c for c, _ in stage]
    non_key = [c for c in cols if c not in keys]
    sel = lambda c: EXPR.get(c, f"S.{c}")  # noqa: E731
    on = " AND ".join([f"T.{k} = S.{k}" for k in keys] + ["T.slot_time = @slot_time"])
    insert_cols = cols + list(insert_only or {})
    insert_vals = [sel(c) for c in cols] + list((insert_only or {}).values())
    matched = f" AND (S.{guard} IS NOT NULL OR T.{guard} IS NULL)" if guard else ""
    return (
        f"MERGE `{target}` T\nUSING `{source}` S\nON {on}\n"
        f"WHEN MATCHED{matched} THEN UPDATE SET {', '.join(f'{c} = {sel(c)}' for c in non_key)}\n"
        f"WHEN NOT MATCHED THEN INSERT ({', '.join(insert_cols)}) VALUES ({', '.join(insert_vals)})"
    )


def check_unique(rows, keys):
    seen = set()
    for r in rows:
        k = tuple(r[c] for c in keys)
        if k in seen:
            raise ValueError(f"duplicate key {k}: a MERGE source must have one row per key")
        seen.add(k)


def _client(project, location):
    from google.cloud import bigquery
    return bigquery.Client(project=project, location=location)


def read_active_routes(project, dataset, location):
    """Active routes as dicts in the shape traffic.group_calls expects."""
    client = _client(project, location)
    rows = client.query(ROUTES_SQL.format(project=project, dataset=dataset)).result()
    return [dict(r.items()) for r in rows]


def _merge_table(client, project, dataset, table, stage, keys, insert_only, guard, rows, slot):
    from google.cloud import bigquery
    check_unique(rows, keys)
    staging = f"{project}.{dataset}._stg_{table}_{uuid.uuid4().hex[:12]}"
    schema = [bigquery.SchemaField(c, t) for c, t in stage]
    tbl = bigquery.Table(staging, schema=schema)
    tbl.expires = utc_now() + timedelta(hours=1)  # cleans itself up even if this process dies
    client.create_table(tbl)
    try:
        names = [c for c, _ in stage]
        client.load_table_from_json(
            [{c: r[c] for c in names} for r in rows], staging,
            job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_APPEND"),
        ).result()
        sql = merge_sql(f"{project}.{dataset}.{table}", staging, stage, keys, insert_only, guard)
        client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("slot_time", "TIMESTAMP", slot)])).result()
    finally:
        client.delete_table(staging, not_found_ok=True)


def write_rows(project, dataset, location, slot, traffic_rows, weather_rows):
    """One MERGE per table. Empty row lists are skipped."""
    client = _client(project, location)
    if traffic_rows:
        _merge_table(client, project, dataset, "traffic_snapshots", TRAFFIC_STAGE, TRAFFIC_KEYS,
                     TRAFFIC_INSERT_ONLY, TRAFFIC_GUARD, traffic_rows, slot)
    if weather_rows:
        _merge_table(client, project, dataset, "weather_slots", WEATHER_STAGE, WEATHER_KEYS,
                     None, WEATHER_GUARD, weather_rows, slot)
